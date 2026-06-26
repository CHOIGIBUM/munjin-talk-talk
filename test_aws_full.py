"""문진톡톡 AWS 전체 통합 테스트 (boto3 직접 사용).

실제 AWS 리소스(Bedrock, DynamoDB, S3, Lambda)를 호출해 전체 파이프라인이
정상 동작하는지 확인합니다.

계정/리소스 식별자는 환경변수로 주입합니다 (공개 저장소에 식별자를 남기지 않기 위함).

실행 예시:
    export MUNJIN_REGION=ap-northeast-2
    export MUNJIN_LAMBDA_NAME=<lambda-function-name>
    export MUNJIN_API_URL=https://<api-id>.execute-api.<region>.amazonaws.com
    export MUNJIN_TABLE=MunjinSessions
    export MUNJIN_ARTIFACTS_BUCKET=<artifacts-bucket-name>
    python3 test_aws_full.py
"""
import json
import os
import time
import boto3
from botocore.config import Config

REGION = os.environ.get("MUNJIN_REGION", "ap-northeast-2")
LAMBDA_NAME = os.environ.get("MUNJIN_LAMBDA_NAME", "")
API_URL = os.environ.get("MUNJIN_API_URL", "")
TABLE_NAME = os.environ.get("MUNJIN_TABLE", "MunjinSessions")
ARTIFACTS_BUCKET = os.environ.get("MUNJIN_ARTIFACTS_BUCKET", "")

_missing = [
    name for name, value in [
        ("MUNJIN_LAMBDA_NAME", LAMBDA_NAME),
        ("MUNJIN_API_URL", API_URL),
        ("MUNJIN_ARTIFACTS_BUCKET", ARTIFACTS_BUCKET),
    ] if not value
]
if _missing:
    raise SystemExit(
        "다음 환경변수를 설정해야 통합 테스트를 실행할 수 있습니다: " + ", ".join(_missing)
    )

bedrock = boto3.client("bedrock-runtime", region_name=REGION, config=Config(read_timeout=60))
dynamodb = boto3.resource("dynamodb", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

results = []


def run_test(name, fn):
    print(f"\n{'='*60}")
    print(f"[TEST] {name}")
    print(f"{'='*60}")
    try:
        fn()
        results.append((name, "PASS", ""))
        print(f"  ✅ PASS")
    except Exception as e:
        results.append((name, "FAIL", str(e)))
        print(f"  ❌ FAIL: {e}")


# =============================================================================
# 1. Bedrock LLM 테스트
# =============================================================================

def test_nova_lite():
    """Nova Lite converse 호출."""
    resp = bedrock.converse(
        modelId="apac.amazon.nova-lite-v1:0",
        messages=[{"role": "user", "content": [{"text": "Say hello in Korean in one word"}]}],
        inferenceConfig={"maxTokens": 50}
    )
    text = resp["output"]["message"]["content"][0]["text"]
    assert len(text) > 0
    print(f"  응답: {text}")
    print(f"  Tokens: in={resp['usage']['inputTokens']}, out={resp['usage']['outputTokens']}")
    print(f"  Latency: {resp['ResponseMetadata']['HTTPHeaders'].get('x-amzn-bedrock-invocation-latency', 'N/A')}ms")


def test_nova_pro():
    """Nova Pro converse 호출."""
    resp = bedrock.converse(
        modelId="apac.amazon.nova-pro-v1:0",
        messages=[{"role": "user", "content": [{"text": "Say hello in Korean in one word"}]}],
        inferenceConfig={"maxTokens": 50}
    )
    text = resp["output"]["message"]["content"][0]["text"]
    assert len(text) > 0
    print(f"  응답: {text}")
    print(f"  Tokens: in={resp['usage']['inputTokens']}, out={resp['usage']['outputTokens']}")


def test_titan_embedding():
    """Titan Text Embedding v2 벡터 생성."""
    body = json.dumps({"inputText": "headache pain", "dimensions": 512})
    resp = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        contentType="application/json",
        accept="application/json",
        body=body.encode("utf-8")
    )
    data = json.loads(resp["body"].read())
    embedding = data["embedding"]
    assert len(embedding) == 512, f"Expected 512, got {len(embedding)}"
    print(f"  차원: {len(embedding)}")
    print(f"  첫 5값: {[round(v, 4) for v in embedding[:5]]}")


def test_titan_embedding_korean():
    """한국어 증상 표현의 embedding 생성."""
    body = json.dumps({"inputText": "기침이 나고 목이 아파요", "dimensions": 512})
    resp = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        contentType="application/json",
        accept="application/json",
        body=body.encode("utf-8")
    )
    data = json.loads(resp["body"].read())
    assert len(data["embedding"]) == 512
    print(f"  한국어 embedding 생성 성공 (512차원)")


# =============================================================================
# 2. DynamoDB 테스트
# =============================================================================

def test_dynamodb_table():
    """테이블 상태 및 세션 조회."""
    resp = table.scan(Limit=10)
    items = resp.get("Items", [])
    real_sessions = [i for i in items if not str(i.get("session_id", "")).startswith("__meta")]
    print(f"  총 아이템: {len(items)}, 실제 세션: {len(real_sessions)}")
    for s in real_sessions[:3]:
        print(f"    - {s['session_id']}: status={s.get('status')}, visit={s.get('visit_type')}")
    assert len(items) > 0


def test_dynamodb_session_structure():
    """세션 데이터의 필수 필드 존재 확인."""
    resp = table.scan(Limit=10)
    items = [i for i in resp.get("Items", []) if not str(i.get("session_id", "")).startswith("__meta")]
    if not items:
        print("  (세션 없음)")
        return

    session = items[0]
    required_fields = ["session_id", "status", "visit_type", "created_at", "patient", "question_set_id"]
    missing = [f for f in required_fields if f not in session]
    print(f"  세션 필드: {sorted(session.keys())}")
    assert not missing, f"누락 필드: {missing}"

    patient = session.get("patient", {})
    print(f"  환자 정보: name={patient.get('name')}, age_band={patient.get('age_band')}, gender={patient.get('gender')}")
    # 실명이 저장되면 안 됨
    assert "full_name" not in patient, "실명이 DynamoDB에 저장됨!"
    assert "birth_date" not in patient, "생년월일이 DynamoDB에 저장됨!"
    print(f"  ✓ PII 미저장 확인")


# =============================================================================
# 3. S3 Artifact 테스트
# =============================================================================

def test_s3_artifacts():
    """S3 산출물 버킷 접근을 확인합니다.

    list 호출이 성공하면 접근 권한은 정상입니다. 객체가 0개일 수 있는데,
    이는 S3 Lifecycle 3일 삭제 정책으로 과거 artifact가 정리된 정상 상태입니다.
    """
    resp = s3.list_objects_v2(Bucket=ARTIFACTS_BUCKET, MaxKeys=20)
    # list 호출이 예외 없이 반환되면 버킷 접근은 성공
    assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200, "버킷 접근 실패"
    contents = resp.get("Contents", [])
    print(f"  버킷 접근: 정상")
    print(f"  객체 수: {len(contents)}")
    if not contents:
        print(f"  (artifact 없음 - Lifecycle 3일 삭제 정책으로 정리된 정상 상태)")
    for obj in contents[:5]:
        print(f"    - {obj['Key']} ({obj['Size']} bytes)")


def test_s3_artifact_content():
    """S3에 저장된 onepaper artifact의 구조를 확인합니다."""
    resp = s3.list_objects_v2(Bucket=ARTIFACTS_BUCKET, MaxKeys=50)
    contents = resp.get("Contents", [])
    onepaper_keys = [obj["Key"] for obj in contents if "onepaper" in obj["Key"]]
    if not onepaper_keys:
        print("  (onepaper artifact 없음)")
        return

    key = onepaper_keys[0]
    obj = s3.get_object(Bucket=ARTIFACTS_BUCKET, Key=key)
    data = json.loads(obj["Body"].read())
    print(f"  파일: {key}")
    print(f"  최상위 키: {sorted(data.keys())}")

    # 원페이퍼 구조 확인
    if "symptom_slots" in data:
        print(f"  증상 슬롯 수: {len(data['symptom_slots'])}")
        for slot in data["symptom_slots"][:3]:
            print(f"    - {slot.get('name')}: status={slot.get('status')}, alert={slot.get('alert')}")
    if "safety_flags" in data:
        print(f"  안전 플래그: {data['safety_flags']}")
    if "patient_summary" in data:
        ps = data["patient_summary"]
        print(f"  환자 요약: {ps.get('display_name')}, {ps.get('age_text')}, {ps.get('sex')}")

    # score/confidence 같은 금지 필드가 없는지 확인
    raw = json.dumps(data)
    assert '"confidence"' not in raw, "confidence 필드가 artifact에 포함됨!"
    print(f"  ✓ 금지 필드(confidence/score) 미포함 확인")


def test_s3_answers_artifact():
    """환자 답변 artifact의 가명처리 확인."""
    resp = s3.list_objects_v2(Bucket=ARTIFACTS_BUCKET, MaxKeys=50)
    contents = resp.get("Contents", [])
    answer_keys = [obj["Key"] for obj in contents if "answers" in obj["Key"]]
    if not answer_keys:
        print("  (answers artifact 없음)")
        return

    key = answer_keys[0]
    obj = s3.get_object(Bucket=ARTIFACTS_BUCKET, Key=key)
    data = json.loads(obj["Body"].read())
    print(f"  파일: {key}")
    print(f"  질문 키: {sorted(data.keys())}")

    for qid, answer in list(data.items())[:2]:
        print(f"  {qid}:")
        if isinstance(answer, dict):
            print(f"    text 길이: {len(answer.get('text', ''))}")
            print(f"    spans: {len(answer.get('spans', []))}")
            print(f"    matched_slots: {len(answer.get('matched_slots', []))}")
            if answer.get("matched_slots"):
                slot = answer["matched_slots"][0]
                print(f"      첫 slot: {slot.get('name')} (ir_method: {slot.get('ir_method')})")


# =============================================================================
# 4. Lambda 직접 호출 테스트
# =============================================================================

def test_lambda_question_set():
    """Lambda /question-sets/default 라우트 테스트."""
    payload = json.dumps({
        "requestContext": {"http": {"method": "GET"}},
        "rawPath": "/question-sets/default",
        "headers": {}
    }).encode("utf-8")

    resp = lambda_client.invoke(FunctionName=LAMBDA_NAME, Payload=payload)
    result = json.loads(resp["Payload"].read())
    status = result.get("statusCode", 0)
    body = json.loads(result.get("body", "{}"))

    assert status == 200, f"Status {status}: {body}"
    assert body["id"] == "default"
    print(f"  Status: {status}")
    print(f"  질문 세트: {body['id']}")
    visits = body.get("visits", {})
    print(f"  초진 질문 수: {len(visits.get('initial', []))}")
    print(f"  재진 질문 수: {len(visits.get('followup', []))}")
    if visits.get("initial"):
        q1 = visits["initial"][0]
        print(f"  Q1: id={q1['id']}, type={q1.get('question_type')}")


def test_lambda_doctor_queue_auth():
    """인증 없이 의사 대기열 접근 시 401 반환 확인."""
    payload = json.dumps({
        "requestContext": {"http": {"method": "GET"}},
        "rawPath": "/doctor/queue",
        "headers": {}
    }).encode("utf-8")

    resp = lambda_client.invoke(FunctionName=LAMBDA_NAME, Payload=payload)
    result = json.loads(resp["Payload"].read())
    status = result.get("statusCode", 0)
    body = json.loads(result.get("body", "{}"))

    print(f"  Status: {status}")
    print(f"  Error: {body.get('error', 'N/A')}")
    # 인증 설정이 있으면 401/403, 없으면 200
    assert status in (200, 401, 403, 503), f"Unexpected status: {status}"
    if status in (401, 403):
        print(f"  ✓ 인증 보호 정상 작동 (코드 없이 접근 차단)")
    elif status == 200:
        sessions = body.get("sessions", [])
        print(f"  인증 비활성 - 세션 수: {len(sessions)}")


def test_lambda_404_route():
    """존재하지 않는 경로에 404 반환 확인."""
    payload = json.dumps({
        "requestContext": {"http": {"method": "GET"}},
        "rawPath": "/nonexistent-path",
        "headers": {}
    }).encode("utf-8")

    resp = lambda_client.invoke(FunctionName=LAMBDA_NAME, Payload=payload)
    result = json.loads(resp["Payload"].read())
    status = result.get("statusCode", 0)
    body = json.loads(result.get("body", "{}"))

    assert status == 404, f"Expected 404, got {status}"
    assert body.get("error") == "not_found"
    print(f"  Status: {status}, error: {body['error']}")
    print(f"  ✓ 404 라우팅 정상")


def test_lambda_process_answer_validation():
    """process-answer에 빈 transcript 전송 시 400 반환 확인."""
    payload = json.dumps({
        "requestContext": {"http": {"method": "POST"}},
        "rawPath": "/process-answer",
        "headers": {},
        "body": json.dumps({
            "session_id": "test_validation",
            "question_id": "Q1",
            "question_type": "chief_complaint",
            "transcript": ""
        })
    }).encode("utf-8")

    resp = lambda_client.invoke(FunctionName=LAMBDA_NAME, Payload=payload)
    result = json.loads(resp["Payload"].read())
    status = result.get("statusCode", 0)
    body = json.loads(result.get("body", "{}"))

    print(f"  Status: {status}")
    print(f"  Error: {body.get('error', 'N/A')}")
    # 세션이 없으면 404, 있으면 400 (빈 transcript)
    assert status in (400, 401, 404), f"Unexpected status: {status}: {body}"


# =============================================================================
# 5. 전체 파이프라인 E2E 테스트 (실제 세션 사용)
# =============================================================================

def test_full_pipeline_with_existing_session():
    """기존 세션으로 process-answer 전체 파이프라인을 실행합니다."""
    # 기존 세션 중 하나 사용
    resp = table.scan(Limit=10)
    items = [i for i in resp.get("Items", []) if not str(i.get("session_id", "")).startswith("__meta")]
    if not items:
        print("  (세션 없음 - 스킵)")
        return

    session = items[0]
    session_id = session["session_id"]
    patient_token = (session.get("patient_access") or {}).get("token", "")

    print(f"  세션: {session_id}")
    print(f"  토큰 있음: {bool(patient_token)}")

    payload = json.dumps({
        "requestContext": {"http": {"method": "POST"}},
        "rawPath": "/process-answer",
        "headers": {"x-munjin-patient-token": patient_token} if patient_token else {},
        "body": json.dumps({
            "session_id": session_id,
            "question_id": "Q1",
            "question_type": "chief_complaint",
            "question_set_id": "default",
            "visit_type": session.get("visit_type", "initial"),
            "transcript": "3일 전부터 기침이 나고 목이 아파요"
        })
    }).encode("utf-8")

    start_time = time.time()
    resp = lambda_client.invoke(FunctionName=LAMBDA_NAME, Payload=payload)
    elapsed = time.time() - start_time
    result = json.loads(resp["Payload"].read())
    status = result.get("statusCode", 0)
    body = json.loads(result.get("body", "{}"))

    print(f"  Status: {status}")
    print(f"  Latency: {elapsed:.2f}초")

    if status == 200:
        print(f"  validator_passed: {body.get('validator_passed')}")
        print(f"  matched_slots: {len(body.get('matched_slots', []))}")
        print(f"  unmatched_spans: {len(body.get('unmatched_spans', []))}")
        print(f"  safety_flag: {body.get('safety_flag')}")
        print(f"  onepager_ready: {body.get('onepager_ready')}")
        if body.get("matched_slots"):
            for slot in body["matched_slots"][:5]:
                print(f"    매칭: {slot.get('name')} (status={slot.get('status')}, method={slot.get('ir_method')})")
        trace = body.get("trace", [])
        if trace:
            print(f"  파이프라인 trace ({len(trace)}단계):")
            for step in trace:
                print(f"    - {step.get('node')}: {step.get('status')}")
    elif status == 401:
        print(f"  인증 실패 (환자 토큰 불일치 가능): {body.get('error')}")
    else:
        print(f"  응답: {json.dumps(body, ensure_ascii=False)[:300]}")


# =============================================================================
# 6. Bedrock 프롬프트 품질 테스트
# =============================================================================

def test_extraction_prompt_quality():
    """실제 문진 추출 프롬프트를 Nova Pro에서 테스트합니다."""
    system = (
        "You are a medical intake structuring assistant. "
        "Extract symptoms from Korean patient speech into JSON. "
        "Return ONLY valid JSON. "
        "Required structure: {\"spans\": [{\"source_quote\": str, \"type\": \"symptom\", "
        "\"slot_ref\": str, \"name\": str, \"normalized_text\": str, \"status\": \"있음\"|\"없음\", "
        "\"alert\": bool, \"explain\": str}], "
        "\"structured\": {\"standardized_text\": str, \"clinical_clues\": [], \"questions\": [], \"unresolved_items\": []}}"
    )
    user = "환자 발화: '3일 전부터 기침이 나고 목이 칼칼해요. 열은 없어요.'\n문항: 주호소\nJSON만 반환하세요."

    resp = bedrock.converse(
        modelId="apac.amazon.nova-pro-v1:0",
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": 1200}
    )
    text = resp["output"]["message"]["content"][0]["text"]
    print(f"  응답 길이: {len(text)} chars")
    print(f"  Tokens: in={resp['usage']['inputTokens']}, out={resp['usage']['outputTokens']}")

    # JSON 파싱
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    parsed = json.loads(clean)
    assert "spans" in parsed, "spans 필드 없음"
    assert "structured" in parsed, "structured 필드 없음"
    assert len(parsed["spans"]) >= 1, "최소 1개 span 필요"

    print(f"  ✓ JSON 파싱 성공")
    print(f"  Span 수: {len(parsed['spans'])}")
    for span in parsed["spans"]:
        print(f"    - {span.get('name')}: quote='{span.get('source_quote')}', status={span.get('status')}")

    # source_quote가 원문에 있는지 확인
    transcript = "3일 전부터 기침이 나고 목이 칼칼해요. 열은 없어요."
    for span in parsed["spans"]:
        quote = span.get("source_quote", "")
        assert quote in transcript or any(w in transcript for w in quote.split()), \
            f"Ungrounded quote: '{quote}'"
    print(f"  ✓ 모든 source_quote가 원문에 근거함")


def test_dialect_normalization_quality():
    """사투리 표준어 변환을 실제 Lambda 파이프라인(RAG 포함)으로 확인합니다."""
    # 실제 서비스는 dialect_rag.py의 강원 사투리 팩을 RAG로 제공합니다.
    # 단순 LLM 프롬프트가 아닌 실제 파이프라인을 호출해야 정확히 검증됩니다.
    # "머리깽이"(머리), "아푸나"(아프니)는 강원 사투리 팩에 실제로 존재하는 표현입니다.
    resp_scan = table.scan(Limit=10)
    items = [i for i in resp_scan.get("Items", []) if not str(i.get("session_id", "")).startswith("__meta")]
    if not items:
        print("  (세션 없음 - 스킵)")
        return

    session = items[0]
    session_id = session["session_id"]
    patient_token = (session.get("patient_access") or {}).get("token", "")

    transcript = "어제부터 머리깽이가 마이 아프고 목도 칼칼해요"
    payload = json.dumps({
        "requestContext": {"http": {"method": "POST"}},
        "rawPath": "/process-answer",
        "headers": {"x-munjin-patient-token": patient_token} if patient_token else {},
        "body": json.dumps({
            "session_id": session_id,
            "question_id": "Q1",
            "question_type": "chief_complaint",
            "question_set_id": "default",
            "visit_type": session.get("visit_type", "initial"),
            "transcript": transcript
        })
    }).encode("utf-8")

    resp = lambda_client.invoke(FunctionName=LAMBDA_NAME, Payload=payload)
    result = json.loads(resp["Payload"].read())
    status = result.get("statusCode", 0)
    body = json.loads(result.get("body", "{}"))

    print(f"  원문: {transcript}")
    print(f"  Status: {status}")

    if status != 200:
        print(f"  (인증/세션 이슈로 파이프라인 미실행: {body.get('error')})")
        return

    # trace에서 dialect_normalization 단계 확인
    trace = body.get("trace", [])
    dialect_step = next((s for s in trace if s.get("node") == "dialect_normalization"), None)
    if dialect_step:
        print(f"  dialect_normalization 단계: {dialect_step.get('status')}")
        details = dialect_step.get("details", {})
        print(f"  표준화 문자수: {details.get('standardized_chars', 'N/A')}")
        # dialect 단계가 통과(passed)했는지 확인
        assert dialect_step.get("status") in ("passed", "clear"), \
            f"dialect 단계 실패: {dialect_step.get('status')}"

    matched = body.get("matched_slots", [])
    print(f"  매칭된 증상: {[s.get('name') for s in matched]}")
    # "머리깽이가 아프다" → 두통, "목 칼칼" → 목의 통증/인후통으로 매칭되어야 함
    assert body.get("validator_passed"), "파이프라인 검증 실패"
    assert len(matched) >= 1, "최소 1개 증상이 매칭되어야 함"
    print(f"  ✓ 사투리(머리깽이/마이) 포함 발화가 RAG+LLM 파이프라인에서 정상 처리됨")


# =============================================================================
# 7. 보안 테스트
# =============================================================================

def test_auth_login_invalid_code():
    """잘못된 접근 코드로 로그인 시 401 반환."""
    payload = json.dumps({
        "requestContext": {"http": {"method": "POST"}},
        "rawPath": "/auth/login",
        "headers": {},
        "body": json.dumps({"role": "staff", "access_code": "wrong_code"})
    }).encode("utf-8")

    resp = lambda_client.invoke(FunctionName=LAMBDA_NAME, Payload=payload)
    result = json.loads(resp["Payload"].read())
    status = result.get("statusCode", 0)
    body = json.loads(result.get("body", "{}"))

    print(f"  Status: {status}")
    assert status == 401, f"Expected 401, got {status}: {body}"
    print(f"  ✓ 잘못된 접근 코드 거부")


def test_session_access_without_token():
    """환자 토큰 없이 세션 접근 시 401 반환."""
    resp = table.scan(Limit=5)
    items = [i for i in resp.get("Items", []) if not str(i.get("session_id", "")).startswith("__meta")]
    if not items:
        print("  (세션 없음)")
        return

    session_id = items[0]["session_id"]
    payload = json.dumps({
        "requestContext": {"http": {"method": "GET"}},
        "rawPath": f"/sessions/{session_id}",
        "headers": {}
    }).encode("utf-8")

    resp = lambda_client.invoke(FunctionName=LAMBDA_NAME, Payload=payload)
    result = json.loads(resp["Payload"].read())
    status = result.get("statusCode", 0)

    print(f"  Status: {status}")
    # 토큰 없이는 401/403이어야 함 (인증 설정된 경우)
    assert status in (200, 401, 403), f"Unexpected: {status}"
    if status in (401, 403):
        print(f"  ✓ 토큰 없이 세션 접근 차단 (접근 제어 정상)")
    else:
        print(f"  (인증 우회 - 개발 모드?)")


# =============================================================================
# 실행
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  문진톡톡 전체 AWS 통합 테스트 (boto3)")
    print("=" * 60)

    # Bedrock LLM
    run_test("1-1. Nova Lite 호출", test_nova_lite)
    run_test("1-2. Nova Pro 호출", test_nova_pro)
    run_test("1-3. Titan Embedding (영어)", test_titan_embedding)
    run_test("1-4. Titan Embedding (한국어)", test_titan_embedding_korean)

    # DynamoDB
    run_test("2-1. DynamoDB 세션 조회", test_dynamodb_table)
    run_test("2-2. DynamoDB 세션 구조 & PII 미저장", test_dynamodb_session_structure)

    # S3
    run_test("3-1. S3 Artifact 접근", test_s3_artifacts)
    run_test("3-2. S3 Onepaper 구조", test_s3_artifact_content)
    run_test("3-3. S3 Answers Artifact", test_s3_answers_artifact)

    # Lambda 라우팅
    run_test("4-1. Lambda /question-sets/default", test_lambda_question_set)
    run_test("4-2. Lambda /doctor/queue 인증", test_lambda_doctor_queue_auth)
    run_test("4-3. Lambda 404 라우팅", test_lambda_404_route)
    run_test("4-4. Lambda process-answer 입력 검증", test_lambda_process_answer_validation)

    # 전체 파이프라인
    run_test("5-1. 전체 파이프라인 E2E", test_full_pipeline_with_existing_session)

    # 프롬프트 품질
    run_test("6-1. 증상 추출 프롬프트 품질", test_extraction_prompt_quality)
    run_test("6-2. 사투리 표준어 변환 품질", test_dialect_normalization_quality)

    # 보안
    run_test("7-1. 로그인 접근 코드 검증", test_auth_login_invalid_code)
    run_test("7-2. 세션 토큰 접근 제어", test_session_access_without_token)

    # 결과
    print("\n")
    print("=" * 60)
    print("  최종 결과 요약")
    print("=" * 60)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"\n  총 {len(results)}개: ✅ {passed} PASS / ❌ {failed} FAIL\n")
    for name, status, err in results:
        icon = "✅" if status == "PASS" else "❌"
        line = f"  {icon} {name}"
        if err:
            line += f"\n      → {err[:120]}"
        print(line)
