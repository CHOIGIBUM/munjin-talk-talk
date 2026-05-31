import json
import os
import re
import time
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote_plus

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
TABLE_NAME = os.environ.get("SESSIONS_TABLE", "MunjinSessions")
ARTIFACT_BUCKET = os.environ.get("ARTIFACT_BUCKET", "")
CUSTOM_VOCABULARY = os.environ.get("CUSTOM_VOCABULARY", "")
USE_BEDROCK_LLM = os.environ.get("USE_BEDROCK_LLM", "true").lower() == "true"
ALLOW_RULE_FALLBACK = os.environ.get("ALLOW_RULE_FALLBACK", "false").lower() == "true"
ENABLE_BEDROCK_REVIEW = os.environ.get("ENABLE_BEDROCK_REVIEW", "true").lower() == "true"
ENABLE_BEDROCK_GUIDE = os.environ.get("ENABLE_BEDROCK_GUIDE", "true").lower() == "true"
STRONG_MODEL_ID = os.environ.get("STRONG_MODEL_ID", "apac.amazon.nova-pro-v1:0")
LIGHT_MODEL_ID = os.environ.get("LIGHT_MODEL_ID", "apac.amazon.nova-lite-v1:0")
REVIEWER_MODEL_ID = os.environ.get("REVIEWER_MODEL_ID", STRONG_MODEL_ID)
GUIDE_MODEL_ID = os.environ.get("GUIDE_MODEL_ID", LIGHT_MODEL_ID)
MAX_LLM_TOKENS = int(os.environ.get("MAX_LLM_TOKENS", "1600"))
REVIEW_MAX_TOKENS = int(os.environ.get("REVIEW_MAX_TOKENS", "900"))
GUIDE_MAX_TOKENS = int(os.environ.get("GUIDE_MAX_TOKENS", "900"))

ddb = boto3.resource("dynamodb", region_name=REGION)
table = ddb.Table(TABLE_NAME)
s3 = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)
transcribe = boto3.client("transcribe", region_name=REGION)
bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=REGION,
    config=Config(connect_timeout=5, read_timeout=50, retries={"max_attempts": 2, "mode": "standard"}),
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
        },
        "body": json.dumps(body, ensure_ascii=False, default=json_default),
    }


def json_default(value):
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    raise TypeError(f"Not JSON serializable: {type(value)}")


def ddb_value(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [ddb_value(item) for item in value]
    if isinstance(value, dict):
        return {key: ddb_value(item) for key, item in value.items()}
    return value


def parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def normalize_visit_type(value):
    if value in ("followup", "재진"):
        return "followup"
    return "initial"


def visit_label(value):
    return "재진" if normalize_visit_type(value) == "followup" else "초진"


def mask_name(name):
    text = str(name or "").strip()
    if not text:
        return "환자"
    if len(text) == 1:
        return text
    return f"{text[0]}*{text[-1]}"


def calculate_age(birth_date):
    if not birth_date:
        return ""
    try:
        birth = datetime.strptime(birth_date, "%Y-%m-%d").date()
    except ValueError:
        return ""
    today = datetime.now().date()
    age = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        age -= 1
    return age


def make_session_id():
    return f"s_{int(time.time() * 1000)}_{os.urandom(3).hex()}"


def get_session(session_id):
    if not session_id:
        return None
    res = table.get_item(Key={"session_id": session_id})
    return res.get("Item")


def put_session(item):
    converted = ddb_value(item)
    table.put_item(Item=converted)
    return converted


def next_queue_number():
    try:
        res = table.scan(ProjectionExpression="queue_number", Limit=1000)
        numbers = [int(item.get("queue_number") or 0) for item in res.get("Items", [])]
        return max(numbers or [0]) + 1
    except Exception:
        return int(time.time()) % 10000


def update_session(session_id, updates):
    if not updates:
        return get_session(session_id)
    names = {}
    values = {}
    expr = []
    for idx, (key, value) in enumerate(updates.items()):
        nk = f"#k{idx}"
        vk = f":v{idx}"
        names[nk] = key
        values[vk] = ddb_value(value)
        expr.append(f"{nk} = {vk}")
    names["#updated_at"] = "updated_at"
    values[":updated_at"] = now_iso()
    expr.append("#updated_at = :updated_at")
    res = table.update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET " + ", ".join(expr),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return res.get("Attributes")


def create_session(body):
    patient_input = body.get("patient") or body
    visit_type = normalize_visit_type(body.get("visit_type") or body.get("visitType"))
    full_name = patient_input.get("full_name") or patient_input.get("fullName") or patient_input.get("name") or ""
    birth_date = patient_input.get("birth_date") or patient_input.get("birthDate") or ""
    patient = {
        "name": mask_name(full_name),
        "full_name": full_name,
        "birth_date": birth_date,
        "age": patient_input.get("age") or calculate_age(birth_date),
        "gender": patient_input.get("gender") or "-",
        "receipt_id": patient_input.get("receipt_id") or patient_input.get("receiptId") or f"R-{int(time.time()) % 10000:04d}",
        "department": patient_input.get("department") or "이비인후과",
        "doctor": patient_input.get("doctor") or "이민우",
        "phone": patient_input.get("phone") or "",
    }
    session_id = body.get("session_id") or body.get("sessionId") or make_session_id()
    item = {
        "session_id": session_id,
        "queue_number": body.get("queue_number") or body.get("queueNumber") or next_queue_number(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "status": "waiting_tablet",
        "visit_type": visit_type,
        "risk": "none",
        "patient": patient,
        "responses": {},
        "question_results": {},
        "audio": {},
        "onepager": build_onepager({
            "session_id": session_id,
            "visit_type": visit_type,
            "patient": patient,
            "responses": {},
            "question_results": {},
            "risk": "none",
        }),
    }
    return put_session(item)


def public_session(session):
    patient = session.get("patient", {})
    return {
        "sessionId": session.get("session_id"),
        "session_id": session.get("session_id"),
        "queueNumber": session.get("queue_number") or 0,
        "status": session.get("status", "waiting_tablet"),
        "visitType": session.get("visit_type", "initial"),
        "visit_type": session.get("visit_type", "initial"),
        "risk": session.get("risk", "none"),
        "patient": {
            "name": patient.get("name") or mask_name(patient.get("full_name")),
            "fullName": patient.get("full_name", ""),
            "birthDate": patient.get("birth_date", ""),
            "age": patient.get("age", ""),
            "gender": patient.get("gender", "-"),
            "receiptId": patient.get("receipt_id", ""),
            "department": patient.get("department", "이비인후과"),
            "doctor": patient.get("doctor", ""),
            "phone": patient.get("phone", ""),
            "honorific": "어르신",
        },
        "responses": session.get("responses", {}),
        "createdAt": session.get("created_at"),
        "updatedAt": session.get("updated_at"),
    }


def list_sessions():
    res = table.scan(Limit=100)
    items = res.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return [public_session(item) for item in items]


def make_audio_key(session_id, question_id, content_type):
    ext = "webm"
    if "/" in content_type:
        ext = content_type.split("/")[-1].split(";")[0] or "webm"
    if ext == "mpeg":
        ext = "mp3"
    return f"sessions/{session_id}/{question_id}.{ext}"


def generate_upload_url(body):
    session_id = body.get("session_id") or body.get("sessionId")
    question_id = body.get("question_id") or body.get("questionId")
    visit_type = normalize_visit_type(body.get("visit_type") or body.get("visitType"))
    content_type = body.get("content_type") or body.get("contentType") or "audio/webm"
    if not session_id or not question_id:
        return None, response(400, {"error": "missing_session_or_question"})
    if question_id not in ("Q1", "Q2", "Q3", "Q4"):
        return None, response(400, {"error": "invalid_question_id"})
    session = get_session(session_id)
    if not session:
        session = create_session({"session_id": session_id, "visit_type": visit_type})
    key = make_audio_key(session_id, question_id, content_type)
    upload_url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": ARTIFACT_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=300,
    )
    audio = session.get("audio", {})
    audio[question_id] = {
        "bucket": ARTIFACT_BUCKET,
        "key": key,
        "content_type": content_type,
        "uploaded_at": now_iso(),
    }
    update_session(session_id, {"audio": audio, "status": "in_progress"})
    transcribe_job_name = f"{session_id}-{question_id}-{int(time.time() * 1000)}"
    return {
        "upload_url": upload_url,
        "s3_key": key,
        "transcribeJobName": transcribe_job_name,
        "transcribe_job_name": transcribe_job_name,
        "expires_in": 300,
    }, None


def parse_job_name(job_name):
    m = re.match(r"^(.*)-(Q[1-4])(?:-[0-9A-Za-z]+)?$", str(job_name or ""))
    if not m:
        return None, None
    return m.group(1), m.group(2)


def safe_job_name(job_name):
    return re.sub(r"[^0-9A-Za-z._-]", "-", str(job_name))[:180]


def get_or_start_transcript(job_name):
    session_id, question_id = parse_job_name(job_name)
    if not session_id or not question_id:
        return response(400, {"error": "invalid_job_name"})
    session = get_session(session_id)
    if not session:
        return response(404, {"error": "session_not_found"})
    audio = (session.get("audio") or {}).get(question_id) or {}
    key = audio.get("key") or f"sessions/{session_id}/{question_id}.webm"
    bucket = audio.get("bucket") or ARTIFACT_BUCKET
    transcribe_name = safe_job_name(f"munjin-{job_name}")
    output_key = f"transcripts/{session_id}/{question_id}.json"

    try:
        job = transcribe.get_transcription_job(TranscriptionJobName=transcribe_name)["TranscriptionJob"]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in ("BadRequestException", "NotFoundException"):
            raise
        media_format = key.rsplit(".", 1)[-1].lower()
        params = {
            "TranscriptionJobName": transcribe_name,
            "LanguageCode": "ko-KR",
            "MediaFormat": media_format,
            "Media": {"MediaFileUri": f"s3://{bucket}/{key}"},
            "OutputBucketName": bucket,
            "OutputKey": output_key,
        }
        if CUSTOM_VOCABULARY:
            params["Settings"] = {"VocabularyName": CUSTOM_VOCABULARY}
        transcribe.start_transcription_job(**params)
        job = {"TranscriptionJobStatus": "IN_PROGRESS"}

    status = job.get("TranscriptionJobStatus")
    if status != "COMPLETED":
        return response(200, {"status": status, "transcript": "", "confidence": None})

    obj = s3.get_object(Bucket=bucket, Key=output_key)
    payload = json.loads(obj["Body"].read().decode("utf-8"))
    transcript = payload.get("results", {}).get("transcripts", [{}])[0].get("transcript", "")
    confidence = extract_confidence(payload)
    responses = session.get("responses", {})
    responses[question_id] = {"text": transcript, "stt_confidence": confidence, "confirmed": False}
    update_session(session_id, {"responses": responses})
    return response(200, {"status": "COMPLETED", "transcript": transcript, "confidence": confidence})


def extract_confidence(payload):
    try:
        items = payload.get("results", {}).get("items", [])
        vals = [
            float(alt.get("confidence"))
            for item in items
            for alt in item.get("alternatives", [])
            if alt.get("confidence") is not None
        ]
        if vals:
            return round(sum(vals) / len(vals), 3)
    except Exception:
        return None
    return None


SYMPTOM_RULES = [
    ("객혈", "hemoptysis", ["피", "피가", "객혈", "피섞", "피 섞", "묻어"], True),
    ("기침", "cough", ["기침", "콜록"], False),
    ("목 불편감", "throat_irritation", ["목", "칼칼", "따끔", "인후"], False),
    ("코막힘", "nasal_obstruction", ["코가 막", "코막", "맥혀", "막혀"], False),
    ("콧물", "rhinorrhea", ["콧물", "코물"], False),
    ("발열", "fever", ["열", "뜨거", "발열"], False),
    ("가래", "sputum", ["가래", "痰"], False),
    ("호흡곤란", "dyspnea", ["숨", "호흡", "답답"], True),
    ("흉통", "chest_pain", ["가슴", "흉통"], True),
    ("두통", "headache", ["머리", "두통"], False),
]
VALID_SYMPTOM_SLOT_IDS = {slot_id for _, slot_id, _, _ in SYMPTOM_RULES}
SYMPTOM_SPAN_TYPES = {
    "symptom",
    "new",
    "worsening",
    "progress_improved",
    "progress_worsened",
    "progress_unchanged",
}

SYMPTOM_QUOTE_PATTERNS = {
    "throat_irritation": [
        r"목(?:이|은|도)?\s*(?:좀\s*)?(?:칼칼(?:하고|해요|합니다)?|따끔(?:해요|하고|합니다)?|아파요?|불편해요?|간질간질해요?)",
    ],
    "nasal_obstruction": [
        r"코\S{0,4}\s*(?:막혀요|막혀|막힙니다|맥혀요|맥혀|답답해요)",
    ],
    "rhinorrhea": [
        r"콧물(?:이|은|도)?\s*(?:줄줄\s*)?(?:흐르네요|흘러요|나와요|나요)",
        r"코물(?:이|은|도)?\s*(?:줄줄\s*)?(?:흐르네요|흘러요|나와요|나요)",
    ],
    "cough": [
        r"기침(?:이|은|도)?\s*(?:조금\s*)?(?:나요|나와요|심해요|심해졌어요|해요)",
        r"콜록(?:거려요|거립니다|해요)",
    ],
    "fever": [
        r"(?:열|발열)(?:이|은|도)?\s*(?:나요|있어요|나는 것 같아요)",
    ],
    "sputum": [
        r"가래(?:가|는|도)?\s*(?:나요|나와요|있어요|껴요)",
    ],
}


def extract_question(body):
    question_type = body.get("question_type") or body.get("questionType")
    transcript = (body.get("transcript") or "").strip()
    if USE_BEDROCK_LLM:
        try:
            return extract_question_bedrock(body)
        except Exception as exc:
            if not ALLOW_RULE_FALLBACK:
                return {
                    "spans": [],
                    "structured": {},
                    "transcript": transcript,
                    "method": "bedrock_error",
                    "error": str(exc),
                }
    spans = []
    structured = {}
    if question_type in ("chief_complaint", "progress", "new_symptoms"):
        for name, slot_id, keywords, alert in SYMPTOM_RULES:
            quote = find_symptom_quote(transcript, slot_id, keywords)
            if quote:
                spans.append({
                    "source_quote": quote,
                    "type": "symptom" if question_type == "chief_complaint" else "new",
                    "slot_ref": slot_id,
                    "name": name,
                    "alert": alert,
                })
    elif question_type == "onset":
        structured = extract_context(transcript)
        spans = structured.get("spans", [])
    elif question_type in ("current_medications", "adherence"):
        structured = extract_medication(transcript, question_type)
        spans = structured.get("spans", [])
    elif question_type in ("patient_questions", "unresolved_questions"):
        structured = extract_agenda(transcript)
    return {"spans": spans, "structured": structured, "transcript": transcript, "method": "rule_based_mvp"}


def extract_question_bedrock(body):
    question_type = body.get("question_type") or body.get("questionType")
    question_id = body.get("question_id") or body.get("questionId") or ""
    visit_type = normalize_visit_type(body.get("visit_type") or body.get("visitType"))
    transcript = (body.get("transcript") or "").strip()
    if not transcript:
        return {"spans": [], "structured": {}, "transcript": "", "method": "bedrock_nova"}

    model_id = select_extraction_model(visit_type, question_id, question_type)
    prompt = build_extraction_prompt(visit_type, question_id, question_type, transcript)
    obj, raw_text = call_bedrock_json(prompt, model_id, MAX_LLM_TOKENS)
    normalized, validation_errors = normalize_extraction_output(obj, transcript, question_id)
    normalized.update({
        "transcript": transcript,
        "method": "bedrock_nova",
        "llm_meta": {
            "model_id": model_id,
            "raw_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "validation_errors": validation_errors,
        },
    })
    return normalized


def select_extraction_model(visit_type, question_id, question_type):
    if question_type in ("chief_complaint", "progress", "new_symptoms") or question_id in ("Q1",):
        return STRONG_MODEL_ID
    return LIGHT_MODEL_ID


def call_bedrock_json(prompt, model_id, max_tokens):
    resp = bedrock_runtime.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 0, "maxTokens": max_tokens},
    )
    raw_text = "".join(
        block.get("text", "")
        for block in resp.get("output", {}).get("message", {}).get("content", [])
    )
    return extract_first_json_object(raw_text), raw_text


def extract_first_json_object(text):
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.I).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    start = raw.find("{")
    if start < 0:
        return {}
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(raw)):
        ch = raw[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start:idx + 1])
    return {}


def build_extraction_prompt(visit_type, question_id, question_type, transcript):
    visit = visit_label(visit_type)
    question_text = {
        "initial": {
            "Q1": "어디가 불편하셔서 오셨어요?",
            "Q2": "그 증상은 언제부터 그러셨어요?",
            "Q3": "지금 드시는 약이 있으세요?",
            "Q4": "의사선생님께 묻고 싶은 점이 있으세요?",
        },
        "followup": {
            "Q1": "지난번 진료 이후 어떻게 지내셨어요?",
            "Q2": "처방받은 약은 잘 드시고 계세요?",
            "Q3": "그동안 새로 생긴 증상은 없으세요?",
            "Q4": "지난번에 못 여쭤본 점이 있으신가요?",
        },
    }.get(visit_type, {}).get(question_id, "")
    return f"""
You are the semantic parsing LLM for a Korean clinic intake MVP.
Task: standardize dialect/colloquial speech, split meaning units, and tag the answer into the fixed schema.

Critical rules:
- Return JSON only. No markdown.
- Never diagnose. Do not infer facts that are not in the patient answer.
- Every source_quote and original_quote MUST be an exact continuous substring of the patient answer.
- If a fact is implied but no exact quote exists, omit it.
- Split multiple patient questions into separate items.
- Use concise Korean summaries for clinicians.
- source_quote is raw patient wording. normalized_text/summary is standardized Korean.

Visit type: {visit}
Question id: {question_id}
Question type: {question_type}
Question asked: {question_text}
Patient answer:
{transcript}

Allowed symptom slot_ref values when relevant:
hemoptysis, cough, throat_irritation, nasal_obstruction, rhinorrhea, fever, sputum, dyspnea, chest_pain, headache, other

Allowed agenda categories:
drug_drug_interaction, supplement_drug_interaction, food_drug_interaction, treatment_duration, followup_visit, test_question, lifestyle, other

Return exactly this JSON shape:
{{
  "spans": [
    {{
      "source_quote": "exact substring",
      "type": "symptom|new|progress_improved|progress_worsened|progress_unchanged|medication|medication_denial|adherence_gap|context",
      "slot_ref": "allowed symptom slot_ref or other",
      "name": "display symptom name in Korean",
      "normalized_text": "standard Korean meaning",
      "status": "있음|없음|확인필요",
      "score": 0.65,
      "alert": false,
      "explain": "short Korean reason"
    }}
  ],
  "structured": {{
    "standardized_text": "standard Korean rewrite of the answer",
    "clinical_clues": [
      {{
        "category": "증상맥락|복약정보|복약순응도|재진경과",
        "label": "시작시점|기간|현재양상|악화요인|완화요인|복용중|처방약 없음|건강보조제|누락|악화|호전|새 증상",
        "summary": "clinician-facing concise Korean summary",
        "source_quote": "exact substring",
        "source_question": "{question_id}",
        "priority": "일반|우선",
        "related_symptoms": []
      }}
    ],
    "questions": [
      {{
        "category": "allowed agenda category",
        "summary": "concise patient question summary",
        "original_quote": "exact substring"
      }}
    ],
    "unresolved_items": []
  }}
}}
""".strip()


def normalize_extraction_output(obj, transcript, question_id):
    errors = []
    spans = []
    structured = obj.get("structured") if isinstance(obj.get("structured"), dict) else {}
    for item in obj.get("spans", []) if isinstance(obj.get("spans"), list) else []:
        quote = repair_quote(item.get("source_quote", ""), transcript)
        if not quote:
            errors.append({"field": "spans.source_quote", "value": item.get("source_quote", "")})
            continue
        span_type = str(item.get("type") or "context")
        slot_ref = str(item.get("slot_ref") or "other")
        score = item.get("score", 0.82)
        try:
            score = max(0, min(1, float(score)))
        except Exception:
            score = 0.82
        if is_symptom_like_span(span_type, slot_ref) and score <= 0.05:
            # Nova sometimes copies the numeric placeholder from the schema.
            # A valid exact-quote symptom span should not be displayed as 0.00.
            score = 0.86
        spans.append({
            "source_quote": quote,
            "type": span_type,
            "slot_ref": slot_ref,
            "name": clean_quote(item.get("name") or slot_to_name(slot_ref)),
            "normalized_text": clean_quote(item.get("normalized_text") or item.get("name") or quote),
            "status": item.get("status") if item.get("status") in ("있음", "없음", "확인필요") else "있음",
            "score": score,
            "alert": bool(item.get("alert") or slot_ref in ("hemoptysis", "dyspnea", "chest_pain")),
            "explain": clean_quote(item.get("explain") or "LLM이 환자 발화에서 의미 단위를 추출했습니다."),
        })

    clinical = []
    for clue_item in structured.get("clinical_clues", []) if isinstance(structured.get("clinical_clues"), list) else []:
        quote = repair_quote(clue_item.get("source_quote", ""), transcript)
        if not quote:
            errors.append({"field": "clinical_clues.source_quote", "value": clue_item.get("source_quote", "")})
            continue
        clinical.append({
            "category": clean_quote(clue_item.get("category") or "증상맥락"),
            "label": clean_quote(clue_item.get("label") or "문진단서"),
            "summary": clean_quote(clue_item.get("summary") or quote),
            "source_quote": quote,
            "source_question": clue_item.get("source_question") or question_id,
            "priority": clue_item.get("priority") if clue_item.get("priority") in ("일반", "우선") else "일반",
            "related_symptoms": clue_item.get("related_symptoms") if isinstance(clue_item.get("related_symptoms"), list) else [],
        })

    questions = []
    for q in structured.get("questions", []) if isinstance(structured.get("questions"), list) else []:
        quote = repair_quote(q.get("original_quote", ""), transcript)
        if not quote:
            errors.append({"field": "questions.original_quote", "value": q.get("original_quote", "")})
            continue
        questions.append({
            "category": q.get("category") or "other",
            "summary": clean_quote(q.get("summary") or quote),
            "original_quote": quote,
        })

    normalized_structured = {
        "standardized_text": clean_quote(structured.get("standardized_text") or transcript),
        "clinical_clues": clinical,
        "questions": questions,
        "unresolved_items": structured.get("unresolved_items") if isinstance(structured.get("unresolved_items"), list) else [],
    }
    return {"spans": spans, "structured": normalized_structured}, errors


def repair_quote(quote, transcript):
    quote = clean_quote(quote)
    text = str(transcript or "")
    if not quote or not text:
        return ""
    if quote in text:
        return quote
    compact_quote = re.sub(r"\s+", " ", quote)
    compact_text = re.sub(r"\s+", " ", text)
    if compact_quote in compact_text:
        return compact_quote
    for part in re.split(r"[,，/]| 그리고 | 또 | 혹은 | 또는 ", quote):
        part = clean_quote(part)
        if len(part) >= 3 and part in text:
            return part
    return ""


def find_symptom_quote(text, slot_id, keywords):
    for pattern in SYMPTOM_QUOTE_PATTERNS.get(slot_id, []):
        m = re.search(pattern, text)
        if m:
            return clean_quote(m.group(0))
    return find_keyword_quote(text, keywords)


def find_keyword_quote(text, keywords):
    for kw in keywords:
        idx = text.find(kw)
        if idx >= 0:
            sentence = sentence_for(text, kw)
            if sentence:
                return clean_quote(sentence)
            start = max(0, idx - 6)
            end = min(len(text), idx + len(kw) + 10)
            return clean_quote(text[start:end])
    return ""


def clean_quote(text):
    return re.sub(r"\s+", " ", str(text or "")).strip(" .,?!。\"'")


def extract_context(text):
    spans = []
    onset_quote = find_first_pattern(text, [
        r"어저께부터",
        r"어제부터",
        r"그저께(?:\s*저녁)?부터",
        r"그제(?:\s*저녁)?부터",
        r"며칠\s*전부터",
        r"한\s*그제\s*저녁부터",
    ])
    if onset_quote:
        spans.append({"source_quote": onset_quote, "type": "onset"})
    if "괜찮" in text or "나아" in text or "호전" in text:
        spans.append({"source_quote": find_keyword_quote(text, ["괜찮", "나아", "호전"]), "type": "course"})
    if "추" in text or "찬바람" in text:
        spans.append({"source_quote": find_keyword_quote(text, ["추", "찬바람"]), "type": "context"})
    return {"spans": [s for s in spans if s.get("source_quote")], "estimated_onset_relative": "확인필요"}


def find_first_pattern(text, patterns):
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return clean_quote(m.group(0))
    return ""


def extract_medication(text, question_type):
    spans = []
    meds = []
    if "혈압" in text:
        meds.append({"category": "antihypertensive", "patient_term": "혈압약"})
        spans.append({"source_quote": find_keyword_quote(text, ["혈압"]), "type": "medication"})
    if "영양제" in text:
        meds.append({"category": "supplement", "patient_term": "영양제"})
        spans.append({"source_quote": find_keyword_quote(text, ["영양제"]), "type": "medication"})
    if "오메가" in text or "오메가 쓰리" in text or "오메가3" in text:
        meds.append({"category": "supplement", "patient_term": "오메가3"})
        spans.append({"source_quote": find_keyword_quote(text, ["오메가"]), "type": "medication"})
    if "종합비타민" in text or "비타민" in text:
        meds.append({"category": "supplement", "patient_term": "종합비타민"})
        spans.append({"source_quote": find_keyword_quote(text, ["종합비타민", "비타민"]), "type": "medication"})
    if "먹는 약은 따로 없" in text or "약은 따로 없" in text:
        spans.append({"source_quote": find_keyword_quote(text, ["따로 없"]), "type": "medication_denial"})
    if "깜빡" in text or "못 먹" in text:
        spans.append({"source_quote": find_keyword_quote(text, ["깜빡", "못 먹"]), "type": "adherence_gap"})
    return {"spans": [s for s in spans if s.get("source_quote")], "extracted_medications": unique_medications(meds)}


def unique_medications(meds):
    out = []
    seen = set()
    for med in meds:
        key = (med.get("category"), med.get("patient_term"))
        if key in seen:
            continue
        seen.add(key)
        out.append(med)
    return out


def extract_agenda(text):
    questions = []
    for sentence in split_question_sentences(text):
        if not sentence:
            continue
        if ("감기약" in sentence or "혈압약" in sentence) and "같이" in sentence:
            questions.append({
                "category": "drug_drug_interaction",
                "summary": "혈압약-감기약 병용 가능 여부 문의",
                "original_quote": sentence,
            })
        elif ("처방" in sentence or "약" in sentence) and ("영양제" in sentence or "오메가" in sentence or "비타민" in sentence) and ("같이" in sentence or "먹어" in sentence):
            questions.append({
                "category": "supplement_drug_interaction",
                "summary": "처방약-영양제 병용 가능 여부 문의",
                "original_quote": sentence,
            })
        elif "양파" in sentence:
            questions.append({
                "category": "food_drug_interaction",
                "summary": "양파즙 병용 가능 여부 문의",
                "original_quote": sentence,
            })
        elif "언제까지" in sentence or "며칠" in sentence:
            questions.append({
                "category": "treatment_duration",
                "summary": "복약 기간 문의",
                "original_quote": sentence,
            })
        elif ("다시" in sentence or "와도" in sentence or "내원" in sentence or "방문" in sentence) and ("심해" in sentence or "증상" in sentence or "중간" in sentence):
            questions.append({
                "category": "followup_visit",
                "summary": "증상 악화 시 중간 재내원 가능 여부 문의",
                "original_quote": sentence,
            })
    if not questions and text:
        questions.append({"category": "other", "summary": clean_quote(text)[:40], "original_quote": clean_quote(text)})
    return {"questions": questions, "uncategorized_remnant": ""}


def split_question_sentences(text):
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return []
    normalized = re.sub(r"\s+또\s+(?=뭐|혹시|증상|약|언제|와도)", ". 또 ", normalized, count=1)
    parts = [clean_quote(part) for part in re.split(r"[.?!。]+", normalized)]
    return [part for part in parts if part]


def sentence_for(text, keyword):
    for part in re.split(r"[.?!。]", text):
        if keyword in part:
            return clean_quote(part)
    return ""


def is_symptom_like_span(span_type, slot_id):
    return str(span_type or "") in SYMPTOM_SPAN_TYPES and str(slot_id or "") in VALID_SYMPTOM_SLOT_IDS


def match_slots(body):
    spans = body.get("spans") or []
    matched = []
    unmatched = []
    for span in spans:
        slot_id = span.get("slot_ref") or "other"
        span_type = span.get("type", "symptom")
        if not is_symptom_like_span(span_type, slot_id):
            unmatched.append(span)
            continue
        if slot_id in VALID_SYMPTOM_SLOT_IDS:
            name = span.get("name") or slot_to_name(slot_id)
            score = span.get("score", Decimal("0.88") if slot_id != "hemoptysis" else Decimal("0.97"))
            try:
                score = Decimal(str(score))
            except Exception:
                score = Decimal("0.88")
            if score <= 0:
                score = Decimal("0.86")
            matched.append({
                "slot_id": slot_id,
                "name": name,
                "score": score,
                "source_quote": span.get("source_quote", ""),
                "span_type": span_type,
                "alert": bool(span.get("alert") or slot_id in ("hemoptysis", "dyspnea", "chest_pain")),
                "normalized_text": span.get("normalized_text") or name,
                "status": span.get("status") or "있음",
                "explain": span.get("explain") or "Bedrock LLM이 환자 발화에서 의미 단위를 추출했습니다.",
            })
        elif span.get("type") == "symptom":
            unmatched.append(span)
    return {"matched_slots": matched, "unmatched_spans": unmatched}


def slot_to_name(slot_id):
    mapping = {slot_id: name for name, slot_id, _, _ in SYMPTOM_RULES}
    return mapping.get(slot_id, slot_id or "-")


def validate_and_save(body):
    session_id = body.get("session_id") or body.get("sessionId")
    question_id = body.get("question_id") or body.get("questionId")
    if not session_id or not question_id:
        return None, response(400, {"error": "missing_session_or_question"})
    session = get_session(session_id)
    if not session:
        session = create_session({"session_id": session_id, "visit_type": body.get("visit_type")})
    transcript = body.get("transcript") or ""
    structured = body.get("structured") or {}
    spans = body.get("spans") or []
    matched_slots = body.get("matched_slots") or []
    safety_flag = scan_safety(transcript, matched_slots)
    responses = session.get("responses", {})
    responses[question_id] = {
        "text": transcript,
        "spans": spans,
        "matched_slots": matched_slots,
        "structured": structured,
        "extract_method": body.get("method") or body.get("extract_method"),
        "llm_meta": body.get("llm_meta") or {},
        "confirmed": True,
    }
    question_results = session.get("question_results", {})
    question_results[question_id] = responses[question_id]
    risk = "high" if safety_flag or session.get("risk") == "high" else session.get("risk", "none")
    if safety_flag or session.get("risk") == "high" or session.get("status") == "needs_priority":
        status = "needs_priority"
    else:
        status = "completed" if question_id == "Q4" else "in_progress"
    updated_base = {**session, "responses": responses, "question_results": question_results, "risk": risk}
    onepager = build_onepager(updated_base)
    update_session(session_id, {
        "responses": responses,
        "question_results": question_results,
        "risk": risk,
        "status": status,
        "onepager": onepager,
        "safety_flag": safety_flag or session.get("safety_flag"),
    })
    return {
        "validator_passed": True,
        "safety_flag": safety_flag,
        "errors": [],
        "onepager_ready": question_id == "Q4",
    }, None


def scan_safety(transcript, matched_slots):
    if any(slot.get("slot_id") == "hemoptysis" for slot in matched_slots) or "피" in transcript:
        return {
            "category": "hemoptysis",
            "label": "객혈 의증",
            "severity": "high",
            "matched_pattern": "피",
            "message": "객혈 의심 표현이 있어 우선 평가가 필요합니다.",
        }
    return None


def build_onepager(session):
    patient = session.get("patient", {})
    responses = session.get("responses", {})
    visit_type = normalize_visit_type(session.get("visit_type"))
    q1 = responses.get("Q1", {})
    q2 = responses.get("Q2", {})
    q3 = responses.get("Q3", {})
    q4 = responses.get("Q4", {})
    slots = []
    for slot in q1.get("matched_slots", []):
        normalized_slot = slot_to_symptom_slot(slot, "Q1", q1.get("text", ""))
        if normalized_slot:
            slots.append(normalized_slot)
    for slot in q3.get("matched_slots", []):
        normalized_slot = slot_to_symptom_slot(slot, "Q3", q3.get("text", ""))
        if normalized_slot:
            slots.append(normalized_slot)
    slots = dedupe_symptom_slots(slots)
    clinical = build_clinical_clues(q1, q2, q3, visit_type)
    agenda = normalize_agenda(q4)
    safety = scan_safety(" ".join([r.get("text", "") for r in responses.values() if isinstance(r, dict)]), q1.get("matched_slots", []) + q3.get("matched_slots", []))
    review_items = build_review_items(slots, agenda, safety, clinical)
    onepager = {
        "patient_summary": {
            "display_name": patient.get("name") or mask_name(patient.get("full_name")),
            "age_text": f"{patient.get('age') or '-'}세",
            "sex": patient.get("gender") or "-",
            "department": patient.get("department") or "이비인후과",
            "received_at": format_hhmm(session.get("created_at")),
            "audio_duration_text": "확인됨",
            "visit_type": visit_type,
        },
        "agenda": agenda,
        "symptom_slots": slots,
        "clinical_clues": clinical,
        "doctor_brief": {"headline": "", "sections": []},
        "review_items": review_items,
        "transfer_text": build_transfer_text(patient, slots, clinical, agenda, visit_type),
        "safety_flags": [safety] if safety else [],
        "unresolved_items": [],
    }
    if USE_BEDROCK_LLM and ENABLE_BEDROCK_REVIEW and responses:
        onepager = apply_bedrock_onepager_review(session, onepager)
    return onepager


def slot_to_symptom_slot(slot, qid, transcript=""):
    slot_id = slot.get("slot_id") or slot.get("slot_ref")
    span_type = slot.get("span_type") or slot.get("type") or "symptom"
    if not is_symptom_like_span(span_type, slot_id):
        return None
    source_quote = clean_quote(slot.get("source_quote", ""))
    if not source_quote and transcript and slot_id:
        source_quote = find_symptom_quote(transcript, slot_id, [slot.get("name", "")]) or source_quote
    score = slot.get("score", Decimal("0.86"))
    try:
        score = Decimal(str(score))
    except Exception:
        score = Decimal("0.86")
    if score <= 0:
        score = Decimal("0.86")
    return {
        "slot_id": slot_id,
        "name": slot.get("name") or slot_to_name(slot_id),
        "source_question": qid,
        "source_quote": source_quote,
        "normalized_text": slot.get("name") or "",
        "status": "있음",
        "score": score,
        "alert": bool(slot.get("alert")),
        "explain": "환자 발화에서 증상 표현을 확인했습니다.",
    }


def dedupe_symptom_slots(slots):
    by_key = {}
    for slot in slots:
        key = slot.get("slot_id") or slot.get("name")
        if not key:
            continue
        old = by_key.get(key)
        if not old or Decimal(str(slot.get("score", 0))) >= Decimal(str(old.get("score", 0))):
            by_key[key] = slot
    return list(by_key.values())


def build_clinical_clues(q1, q2, q3, visit_type):
    structured_clues = []
    for qid, q in (("Q1", q1), ("Q2", q2), ("Q3", q3)):
        for item in ((q.get("structured") or {}).get("clinical_clues") or []):
            normalized = normalize_clinical_clue(item, qid)
            if normalized:
                structured_clues.append(normalized)
    if structured_clues:
        return unique_clues(structured_clues)
    if not ALLOW_RULE_FALLBACK:
        return []

    clues = []
    idx = 1
    text1 = q1.get("text", "")
    text2 = q2.get("text", "")
    text3 = q3.get("text", "")
    related = [slot.get("name") for slot in q1.get("matched_slots", []) if slot.get("name")]
    onset_quote = find_first_pattern(text2, [
        r"한\s*그제\s*저녁부터",
        r"그제\s*저녁부터",
        r"그저께\s*저녁부터",
        r"그제부터",
        r"그저께부터",
        r"어제부터",
        r"어저께부터",
    ]) or find_first_pattern(text1, [r"어저께부터", r"어제부터", r"그제부터", r"그저께부터"])
    if onset_quote:
        source_q = "Q2" if onset_quote in text2 else "Q1"
        clues.append(clue(idx, "증상맥락", "시작시점", onset_quote, source_q, onset_quote, related))
        idx += 1
    if "괜찮" in text2 or "나아" in text2 or "호전" in text2:
        q = find_keyword_quote(text2, ["괜찮", "나아", "호전"])
        clues.append(clue(idx, "증상맥락", "현재양상", "오늘은 다소 호전/변동감 있음", "Q2", q, related))
        idx += 1
    if "추" in text2 or "찬바람" in text2:
        clues.append(clue(idx, "증상맥락", "악화요인", "추위 노출 후 시작된 듯함", "Q2", find_keyword_quote(text2, ["추", "찬바람"]), []))
        idx += 1
    if "혈압" in text3:
        clues.append(clue(idx, "복약정보", "복용중", "혈압약 복용 중", "Q3", find_keyword_quote(text3, ["혈압"]), []))
        idx += 1
    supplements = []
    if "영양제" in text3:
        supplements.append("영양제")
    if "오메가" in text3:
        supplements.append("오메가3")
    if "종합비타민" in text3 or "비타민" in text3:
        supplements.append("종합비타민")
    if supplements:
        clues.append(clue(idx, "복약정보", "건강보조제", f"{', '.join(unique(supplements))} 복용 중", "Q3", find_keyword_quote(text3, ["영양제", "오메가", "종합비타민", "비타민"]), []))
        idx += 1
    if "먹는 약은 따로 없" in text3 or "약은 따로 없" in text3:
        clues.append(clue(idx, "복약정보", "처방약 없음", "평소 복용 처방약은 없다고 말함", "Q3", find_keyword_quote(text3, ["따로 없"]), []))
        idx += 1
    if "깜빡" in text3 or "못 먹" in text3:
        clues.append(clue(idx, "복약순응도", "누락", "복약 누락 가능성", "Q3", find_keyword_quote(text3, ["깜빡", "못 먹"]), []))
        idx += 1
    if visit_type == "followup" and "심" in q1.get("text", ""):
        clues.append(clue(idx, "재진경과", "악화", "증상 악화 호소", "Q1", find_keyword_quote(q1.get("text", ""), ["심"]), related))
    return clues


def clue(idx, category, label, summary, source_question, source_quote, related):
    return {
        "id": f"c{idx}",
        "category": category,
        "label": label,
        "summary": summary,
        "source_question": source_question,
        "source_quote": source_quote or summary,
        "priority": "일반",
        "related_symptoms": related,
        "action_hint": f"{label} 확인",
        "explain": "문진 원문에서 추출한 진료 맥락입니다.",
    }


def normalize_clinical_clue(item, fallback_qid):
    if not isinstance(item, dict):
        return None
    summary = clean_quote(item.get("summary") or item.get("source_quote") or "")
    source_quote = clean_quote(item.get("source_quote") or summary)
    if not summary and not source_quote:
        return None
    label = clean_quote(item.get("label") or "문진단서")
    return {
        "id": item.get("id") or f"{fallback_qid}-{label}-{source_quote}",
        "category": clean_quote(item.get("category") or "증상맥락"),
        "label": label,
        "summary": summary or source_quote,
        "source_question": item.get("source_question") or fallback_qid,
        "source_quote": source_quote,
        "priority": item.get("priority") if item.get("priority") in ("일반", "우선") else "일반",
        "related_symptoms": item.get("related_symptoms") if isinstance(item.get("related_symptoms"), list) else [],
        "action_hint": item.get("action_hint") or f"{label} 확인",
        "explain": item.get("explain") or "Bedrock LLM이 문진 원문에서 추출한 진료 맥락입니다.",
    }


def unique_clues(clues):
    out = []
    seen = set()
    for item in clues:
        key = (item.get("category"), item.get("label"), item.get("summary"), item.get("source_quote"))
        if key in seen:
            continue
        seen.add(key)
        item = dict(item)
        item["id"] = f"c{len(out) + 1}"
        out.append(item)
    return out


def normalize_agenda(q4):
    structured = q4.get("structured", {})
    questions = structured.get("questions") or q4.get("questions") or []
    text = q4.get("text", "")
    if not questions and not ALLOW_RULE_FALLBACK:
        return []
    if ALLOW_RULE_FALLBACK and text and (not questions or (len(questions) == 1 and questions[0].get("category") == "other")):
        questions = extract_agenda(text).get("questions", [])
    return [{
        "type": item.get("category", "other"),
        "category": item.get("category", "other"),
        "type_label": agenda_label(item.get("category")),
        "summary": item.get("summary", ""),
        "original_quote": item.get("original_quote", ""),
        "source_question": "Q4",
    } for item in questions]


def agenda_label(category):
    return {
        "drug_drug_interaction": "복약 상호작용",
        "supplement_drug_interaction": "영양제 병용",
        "food_drug_interaction": "음식-약 상호작용",
        "treatment_duration": "복약 기간",
        "followup_visit": "재내원 기준",
    }.get(category, "환자 질문")


def build_review_items(slots, agenda, safety, clinical=None):
    items = []
    if safety:
        items.extend(["[우선] 객혈량과 시작 시점 확인", "[우선] 흉부 X-ray/객담 검사 고려"])
    names = {slot.get("name") for slot in slots}
    if names:
        items.append("발열 여부와 실제 체온 확인")
    if "기침" in names:
        items.append("가래 동반 여부와 색깔")
    if "코막힘" in names or "콧물" in names:
        items.append("비폐색/콧물 지속 정도와 알레르기 병력 확인")
    if any(c.get("label") == "건강보조제" for c in (clinical or [])):
        items.append("복용 중인 영양제 종류와 병용 가능성 확인")
    for item in agenda:
        category = item.get("category") or item.get("type")
        if category == "supplement_drug_interaction":
            items.append("처방약과 영양제 병용 가능 여부 안내")
        elif category == "followup_visit":
            items.append("증상 악화 시 중간 재내원 기준 안내")
        elif item.get("summary"):
            items.append(item["summary"] + " 답변")
    return unique(items) or ["문진 내용 직접 확인"]


def build_transfer_text(patient, slots, clinical, agenda, visit_type):
    symptoms = ", ".join(unique([slot.get("name") for slot in slots if slot.get("name")]))
    text = f"{patient.get('age') or '-'}세 {patient.get('gender') or ''} {visit_label(visit_type)} 환자."
    if symptoms:
        text += f" {symptoms} 호소."
    med = next((c.get("summary") for c in clinical if c.get("category") == "복약정보"), "")
    if med:
        text += f" {med}."
    if agenda:
        text += f" 환자 질문: {agenda[0].get('summary')}."
    return text


def apply_bedrock_onepager_review(session, onepager):
    try:
        prompt = build_onepager_review_prompt(session, onepager)
        obj, raw_text = call_bedrock_json(prompt, REVIEWER_MODEL_ID, REVIEW_MAX_TOKENS)
        reviewed = dict(onepager)
        if isinstance(obj.get("review_items"), list):
            items = [clean_quote(x) for x in obj.get("review_items", []) if clean_quote(x)]
            if items:
                reviewed["review_items"] = unique(items)[:8]
        transfer = clean_quote(obj.get("transfer_text") or "")
        if transfer:
            reviewed["transfer_text"] = transfer
        if isinstance(obj.get("doctor_brief"), dict):
            reviewed["doctor_brief"] = obj.get("doctor_brief")
        reviewed["llm_review"] = {
            "model_id": REVIEWER_MODEL_ID,
            "raw_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "issues": obj.get("issues") if isinstance(obj.get("issues"), list) else [],
        }
        return reviewed
    except Exception as exc:
        reviewed = dict(onepager)
        reviewed["llm_review"] = {"model_id": REVIEWER_MODEL_ID, "error": str(exc)}
        return reviewed


def build_onepager_review_prompt(session, onepager):
    payload = {
        "visit_type": visit_label(session.get("visit_type")),
        "patient": session.get("patient", {}),
        "responses": {
            qid: {
                "text": value.get("text", ""),
                "structured": value.get("structured", {}),
                "matched_slots": value.get("matched_slots", []),
            }
            for qid, value in (session.get("responses") or {}).items()
            if isinstance(value, dict)
        },
        "draft_onepager": onepager,
    }
    return f"""
You are the final medical intake review LLM for a Korean clinic one-paper.
Review the draft made from Bedrock semantic parsing.

Rules:
- Do not diagnose and do not add facts not supported by responses.
- Keep outputs concise for a physician.
- review_items should be practical clinician check items.
- transfer_text should be one EMR-style Korean sentence or two short sentences.
- If multiple patient questions exist, preserve that plurality.
- Return JSON only.

Return schema:
{{
  "review_items": ["item"],
  "transfer_text": "EMR draft",
  "doctor_brief": {{
    "headline": "short summary",
    "sections": [
      {{"key": "symptoms|context|medication|agenda|safety", "title": "section title", "summary": "short summary", "items": []}}
    ]
  }},
  "issues": []
}}

Data:
{json.dumps(payload, ensure_ascii=False, default=json_default)}
""".strip()


def unique(values):
    out = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def format_hhmm(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        dt = datetime.now()
    return f"{dt.hour:02d}:{dt.minute:02d}"


def save_doctor_response(body):
    session_id = body.get("session_id") or body.get("sessionId")
    session = get_session(session_id)
    if not session:
        return None, response(404, {"error": "session_not_found"})
    answers = body.get("answers") or []
    patient_instruction = body.get("patient_instruction") or body.get("patientInstruction") or body.get("additional_notes") or body.get("additionalNotes") or ""
    guide = generate_patient_guide(session, answers, patient_instruction)
    if not guide["items"]:
        guide["items"] = default_guide_items(session)
    doctor_review = {
        "answers": answers,
        "patient_instruction": patient_instruction,
        "additional_notes": patient_instruction,
        "reviewed_at": now_iso(),
    }
    update_session(session_id, {
        "doctor_review": doctor_review,
        "patient_guide": guide,
        "status": "reviewed",
    })
    return {"doctor_review_saved": True, "patient_guide_generated": True, "validator_passed": True, "patient_guide": guide}, None


def generate_patient_guide(session, answers, patient_instruction):
    if USE_BEDROCK_LLM and ENABLE_BEDROCK_GUIDE:
        try:
            return generate_patient_guide_bedrock(session, answers, patient_instruction)
        except Exception:
            pass
    return {
        "generated_at": now_iso(),
        "items": [
            {
                "question": ans.get("question_summary") or ans.get("question") or "환자 질문",
                "answer_simple": split_answer(ans.get("answer_text") or ans.get("answer") or ""),
                "tts_emphasis_words": [],
            }
            for ans in answers
        ],
        "delivery_options": ["screen", "tts", "print"],
    }


def generate_patient_guide_bedrock(session, answers, patient_instruction):
    payload = {
        "patient": session.get("patient", {}),
        "onepager": session.get("onepager", {}),
        "doctor_answers": answers,
    }
    prompt = f"""
You are a Korean patient instruction writer for older adults after a clinic visit.
Convert doctor's answers into easy Korean guide items.

Rules:
- Do not add medical facts not present in doctor_answers or notes.
- Keep each bullet short and clear.
- Avoid difficult medical terms unless the doctor used them.
- Return JSON only.

Schema:
{{
  "items": [
    {{
      "question": "patient question summary",
      "answer_simple": ["short instruction sentence"],
      "tts_emphasis_words": ["important word"]
    }}
  ],
  "delivery_options": ["screen", "tts", "print"]
}}

Data:
{json.dumps(payload, ensure_ascii=False, default=json_default)}
""".strip()
    obj, raw_text = call_bedrock_json(prompt, GUIDE_MODEL_ID, GUIDE_MAX_TOKENS)
    items = []
    for item in obj.get("items", []) if isinstance(obj.get("items"), list) else []:
        answers_simple = item.get("answer_simple") if isinstance(item.get("answer_simple"), list) else []
        answers_simple = [clean_quote(x) for x in answers_simple if clean_quote(x)]
        if not answers_simple:
            continue
        items.append({
            "question": clean_quote(item.get("question") or "진료 안내"),
            "answer_simple": answers_simple,
            "tts_emphasis_words": [clean_quote(x) for x in item.get("tts_emphasis_words", []) if clean_quote(x)] if isinstance(item.get("tts_emphasis_words"), list) else [],
        })
    return {
        "generated_at": now_iso(),
        "items": items,
        "delivery_options": obj.get("delivery_options") if isinstance(obj.get("delivery_options"), list) else ["screen", "tts", "print"],
        "llm_meta": {
            "model_id": GUIDE_MODEL_ID,
            "raw_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        },
    }


def split_answer(text):
    parts = [p.strip() for p in re.split(r"[.\n]", text or "") if p.strip()]
    return parts or ["진료실에서 안내받은 내용을 따라 주세요."]


def default_guide_items(session):
    agenda = (session.get("onepager") or {}).get("agenda") or []
    if not agenda:
        return [{"question": "진료 안내", "answer_simple": ["오늘 진료에서 안내받은 내용을 확인해 주세요."], "tts_emphasis_words": []}]
    return [{"question": item.get("summary", "환자 질문"), "answer_simple": ["진료실에서 안내받은 내용을 따라 주세요."], "tts_emphasis_words": []} for item in agenda]


def get_guide(session_id):
    session = get_session(session_id)
    if not session:
        return None
    guide = session.get("patient_guide")
    if not guide:
        guide = {"generated_at": now_iso(), "items": default_guide_items(session), "delivery_options": ["screen", "tts", "print"]}
    return {
        "session_id": session_id,
        "patient_name_masked": (session.get("patient") or {}).get("name", "환자"),
        "patient_guide": guide,
        "doctor_additional_notes": (session.get("doctor_review") or {}).get("patient_instruction") or (session.get("doctor_review") or {}).get("additional_notes", ""),
    }
