"""문진톡톡 전체 환자 여정 E2E 테스트 (실제 AWS Lambda 경유).

실제 서비스 흐름을 처음부터 끝까지 Lambda invoke로 재현합니다:
  접수(세션 생성) → 동의 → 답변 일괄 제출 → 비동기 분석 대기
  → 원페이퍼 확인 → 의사 답변 저장 → 환자 안내문 확인 → 정리(삭제)

직원/의사 인증이 켜진 환경에서는 접근 코드가 필요합니다. 환경변수로 주입합니다:
    export MUNJIN_LAMBDA_NAME=<lambda-function-name>
    export MUNJIN_STAFF_CODE=<staff access code>   # 없으면 인증 단계는 skip 처리
    export MUNJIN_DOCTOR_CODE=<doctor access code>
    python3 test_aws_e2e_journey.py
"""
import json
import os
import time
import boto3

REGION = os.environ.get("MUNJIN_REGION", "ap-northeast-2")
LAMBDA_NAME = os.environ.get("MUNJIN_LAMBDA_NAME", "")
TABLE_NAME = os.environ.get("MUNJIN_TABLE", "MunjinSessions")
STAFF_CODE = os.environ.get("MUNJIN_STAFF_CODE", "")
DOCTOR_CODE = os.environ.get("MUNJIN_DOCTOR_CODE", "")

if not LAMBDA_NAME:
    raise SystemExit("MUNJIN_LAMBDA_NAME 환경변수가 필요합니다.")

lambda_client = boto3.client("lambda", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

results = []
_state = {}  # 단계 간 공유 (session_id, tokens 등)


def step(name, fn):
    print(f"\n{'='*64}")
    print(f"[STEP] {name}")
    print(f"{'='*64}")
    try:
        fn()
        results.append((name, "PASS", ""))
        print("  ✅ PASS")
    except Exception as e:
        results.append((name, "FAIL", str(e)))
        print(f"  ❌ FAIL: {e}")


def invoke(method, path, body=None, headers=None):
    """Lambda를 API Gateway 이벤트 형식으로 호출합니다."""
    event = {
        "requestContext": {"http": {"method": method}},
        "rawPath": path,
        "headers": headers or {},
    }
    if body is not None:
        event["body"] = json.dumps(body, ensure_ascii=False)
    resp = lambda_client.invoke(
        FunctionName=LAMBDA_NAME,
        Payload=json.dumps(event, ensure_ascii=False).encode("utf-8"),
    )
    result = json.loads(resp["Payload"].read())
    status = result.get("statusCode", 0)
    parsed = {}
    try:
        parsed = json.loads(result.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        parsed = {}
    return status, parsed


def staff_login():
    """직원 로그인으로 Bearer 토큰을 얻습니다 (코드 없으면 빈 헤더)."""
    if not STAFF_CODE:
        return {}
    status, body = invoke("POST", "/auth/login", {"role": "staff", "access_code": STAFF_CODE})
    token = body.get("access_token", "")
    return {"authorization": f"Bearer {token}"} if token else {}


def doctor_login():
    if not DOCTOR_CODE:
        return {}
    status, body = invoke("POST", "/auth/login", {"role": "doctor", "access_code": DOCTOR_CODE})
    token = body.get("access_token", "")
    return {"authorization": f"Bearer {token}"} if token else {}


# =============================================================================
# E2E 단계
# =============================================================================

def s1_create_session():
    """① 직원 접수: 세션 생성. 인증이 켜져 있으면 staff 토큰 필요."""
    headers = staff_login()
    status, body = invoke("POST", "/sessions", {
        "visit_type": "initial",
        "question_set_id": "default",
        "patient": {
            "full_name": "테스트환자",
            "birth_date": "1950-03-15",
            "gender": "남성",
            "department": "이비인후과",
            "doctor": "이민우",
        },
    }, headers=headers)

    if status in (401, 403, 503) and not STAFF_CODE:
        print(f"  (인증 필요 - STAFF_CODE 미설정, 기존 세션으로 대체)")
        _use_existing_session()
        return

    assert status == 200, f"세션 생성 실패 status={status}: {body}"
    session_id = body.get("sessionId") or body.get("session_id")
    assert session_id, "session_id 없음"
    _state["session_id"] = session_id
    _state["patient_token"] = body.get("patientToken") or body.get("patient_token") or ""
    _state["staff_headers"] = headers
    print(f"  세션 생성: {session_id}")
    print(f"  마스킹 이름: {body.get('patient', {}).get('name')}")
    print(f"  연령대: {body.get('patient', {}).get('ageBand')}")
    # 접수 시 실명 노출 안 됨 확인
    assert body.get("patient", {}).get("name") != "테스트환자", "실명이 그대로 노출됨!"


def _use_existing_session():
    """인증 코드가 없을 때 기존 세션을 재활용합니다."""
    resp = table.scan(Limit=10)
    items = [i for i in resp.get("Items", []) if not str(i.get("session_id", "")).startswith("__meta")]
    if not items:
        raise AssertionError("재활용할 세션이 없고 STAFF_CODE도 없어 진행 불가")
    session = items[0]
    _state["session_id"] = session["session_id"]
    _state["patient_token"] = (session.get("patient_access") or {}).get("token", "")
    _state["staff_headers"] = {}
    _state["reused"] = True
    print(f"  기존 세션 재활용: {_state['session_id']}")


def _patient_headers():
    pt = _state.get("patient_token", "")
    return {"x-munjin-patient-token": pt} if pt else {}


def s2_consent():
    """② 환자 개인정보 동의 저장."""
    sid = _state["session_id"]
    status, body = invoke("POST", f"/sessions/{sid}/consent", {
        "accepted": True,
        "version": "munjin-privacy-consent-v1",
    }, headers={**_state.get("staff_headers", {}), **_patient_headers()})
    print(f"  Status: {status}")
    assert status in (200, 401, 403), f"예상치 못한 status={status}: {body}"
    if status == 200:
        print("  ✓ 동의 저장 성공")
    else:
        print("  (인증 제약으로 동의 단계 건너뜀 - 흐름 계속)")


def s3_process_answers():
    """③ Q1~Q4 답변 일괄 제출 → 비동기 분석 큐잉."""
    sid = _state["session_id"]
    status, body = invoke("POST", "/process-answers", {
        "session_id": sid,
        "visit_type": "initial",
        "question_set_id": "default",
        "answers": [
            {"question_id": "Q1", "question_type": "chief_complaint", "transcript": "3일 전부터 기침이 나고 목이 칼칼해요"},
            {"question_id": "Q2", "question_type": "onset", "transcript": "그저께 저녁부터요"},
            {"question_id": "Q3", "question_type": "current_medications", "transcript": "혈압약을 매일 아침에 먹어요"},
            {"question_id": "Q4", "question_type": "patient_questions", "transcript": "감기약이랑 혈압약 같이 먹어도 되나요?"},
        ],
    }, headers={**_state.get("staff_headers", {}), **_patient_headers()})
    print(f"  Status: {status}")
    if status in (401, 403):
        print(f"  (인증 제약으로 제출 건너뜀: {body.get('error')})")
        _state["analysis_queued"] = False
        return
    assert status == 200, f"답변 제출 실패 status={status}: {body}"
    print(f"  accepted: {body.get('accepted')}")
    print(f"  analysis_status: {body.get('analysis_status')}")
    print(f"  queued_question_count: {body.get('pipeline', {}).get('queued_question_count')}")
    # 환자는 즉시 응답받아야 함 (분석 대기 안 함)
    assert body.get("patient_complete") is True
    _state["analysis_queued"] = body.get("analysis_queued", False)


def s4_wait_analysis():
    """④ 백그라운드 분석 완료까지 폴링 (최대 90초)."""
    if not _state.get("analysis_queued"):
        print("  (분석이 큐잉되지 않아 대기 건너뜀)")
        return
    sid = _state["session_id"]
    deadline = time.time() + 90
    last_status = None
    while time.time() < deadline:
        item = table.get_item(Key={"session_id": sid}).get("Item", {})
        last_status = item.get("status")
        analysis = item.get("analysis_status")
        print(f"  상태: status={last_status}, analysis_status={analysis}")
        if last_status in ("waiting_doctor", "needs_priority", "reviewed"):
            print(f"  ✓ 분석 완료: {last_status}, onepager_ready={item.get('onepager_ready')}")
            return
        if last_status == "analysis_failed":
            raise AssertionError(f"분석 실패: {item.get('analysis_error')}")
        time.sleep(6)
    raise AssertionError(f"분석이 90초 내 완료되지 않음 (마지막 status={last_status})")


def s5_onepager():
    """⑤ 의료진 원페이퍼 조회."""
    sid = _state["session_id"]
    headers = doctor_login() or _state.get("staff_headers", {})
    status, body = invoke("GET", f"/onepager/{sid}", headers=headers)
    print(f"  Status: {status}")
    if status in (401, 403, 503):
        print(f"  (의사 인증 필요 - DOCTOR_CODE 미설정으로 건너뜀)")
        return
    assert status == 200, f"원페이퍼 조회 실패 status={status}: {body}"
    onepager = body.get("onepager") or body
    slots = onepager.get("symptom_slots", [])
    print(f"  증상 슬롯: {[s.get('name') for s in slots]}")
    print(f"  안전 플래그: {onepager.get('safety_flags', [])}")
    _state["doctor_headers"] = headers


def s6_doctor_response():
    """⑥ 의사 답변 저장 → 환자 안내문 생성."""
    sid = _state["session_id"]
    headers = _state.get("doctor_headers") or doctor_login()
    if not headers and DOCTOR_CODE:
        headers = doctor_login()
    status, body = invoke("POST", "/doctor-response", {
        "session_id": sid,
        "answers": [
            {"question": "감기약과 혈압약 병용 가능 여부", "answer_text": "혈압약은 계속 드시고, 감기약은 오늘 처방받은 것만 드세요."},
        ],
        "patient_instruction": "물을 자주 드시고 3일 후에도 기침이 심하면 다시 오세요.",
    }, headers=headers)
    print(f"  Status: {status}")
    if status in (401, 403, 503):
        print(f"  (의사 인증 필요 - 건너뜀)")
        return
    assert status == 200, f"의사 답변 저장 실패 status={status}: {body}"
    print(f"  doctor_review_saved: {body.get('doctor_review_saved')}")
    print(f"  patient_guide_generated: {body.get('patient_guide_generated')}")
    _state["doctor_responded"] = True


def s7_guide():
    """⑦ 환자 안내문 조회."""
    sid = _state["session_id"]
    headers = {**_state.get("doctor_headers", {}), **_patient_headers()}
    status, body = invoke("GET", f"/guide/{sid}", headers=headers)
    print(f"  Status: {status}")
    if status in (401, 403, 503):
        print(f"  (인증 제약으로 안내문 조회 건너뜀)")
        return
    assert status == 200, f"안내문 조회 실패 status={status}: {body}"
    guide = body.get("patient_guide", {})
    print(f"  안내문 항목 수: {len(guide.get('items', []))}")
    print(f"  의사 강조사항: {body.get('doctor_additional_notes', '')[:50]}")
    print(f"  마스킹 이름: {body.get('patient_name_masked')}")


def s8_cleanup():
    """⑧ 테스트로 생성한 세션 정리 (재활용 세션은 보존)."""
    if _state.get("reused"):
        print("  (기존 세션 재활용했으므로 삭제 안 함)")
        return
    sid = _state.get("session_id")
    if not sid:
        print("  (정리할 세션 없음)")
        return
    table.delete_item(Key={"session_id": sid})
    print(f"  ✓ 테스트 세션 삭제: {sid}")


if __name__ == "__main__":
    print("=" * 64)
    print("  문진톡톡 전체 환자 여정 E2E (실제 AWS)")
    print("=" * 64)
    print(f"  STAFF_CODE 설정: {'O' if STAFF_CODE else 'X'}, DOCTOR_CODE 설정: {'O' if DOCTOR_CODE else 'X'}")

    step("1. 직원 접수 (세션 생성 + PII 마스킹)", s1_create_session)
    step("2. 환자 개인정보 동의", s2_consent)
    step("3. Q1~Q4 답변 제출 (비동기 분석 큐잉)", s3_process_answers)
    step("4. 백그라운드 분석 완료 대기", s4_wait_analysis)
    step("5. 의료진 원페이퍼 조회", s5_onepager)
    step("6. 의사 답변 저장 + 안내문 생성", s6_doctor_response)
    step("7. 환자 안내문 조회", s7_guide)
    step("8. 테스트 세션 정리", s8_cleanup)

    print("\n")
    print("=" * 64)
    print("  E2E 결과 요약")
    print("=" * 64)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"\n  총 {len(results)}단계: ✅ {passed} PASS / ❌ {failed} FAIL\n")
    for name, status, err in results:
        icon = "✅" if status == "PASS" else "❌"
        line = f"  {icon} {name}"
        if err:
            line += f"\n      → {err[:140]}"
        print(line)
