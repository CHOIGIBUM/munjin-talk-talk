"""Amazon Transcribe integration without storing patient audio.

The runtime flow no longer uploads patient voice to S3. Lambda only creates a
short-lived presigned Transcribe Streaming WebSocket URL. The browser streams
PCM audio directly to Amazon Transcribe and sends only confirmed text into the
LLM/IR pipeline.
"""

import uuid
from urllib.parse import urlencode

import boto3
from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest

from settings import CUSTOM_VOCABULARY, REGION
from sessions import create_session, get_session, update_session
from utils import normalize_visit_type, response


def configured_custom_vocabulary():
    """실제 등록된 사용자 어휘집 이름이 있을 때만 Transcribe에 전달합니다."""
    value = str(CUSTOM_VOCABULARY or "").strip()
    if value.lower() in ("", "unused", "none", "null", "-"):
        return ""
    return value


def generate_streaming_transcribe_url(body):
    """Return a presigned WebSocket URL for Amazon Transcribe Streaming.

    This function does not receive or persist audio. It only signs a URL with
    the selected language, PCM encoding, and sample rate.
    """
    session_id = body.get("session_id") or body.get("sessionId")
    question_id = body.get("question_id") or body.get("questionId")
    visit_type = normalize_visit_type(body.get("visit_type") or body.get("visitType"))
    sample_rate = int(body.get("sample_rate") or body.get("sampleRate") or 16000)
    if not session_id or not question_id:
        return None, response(400, {"error": "missing_session_or_question"})
    if question_id not in ("Q1", "Q2", "Q3", "Q4"):
        return None, response(400, {"error": "invalid_question_id"})
    if sample_rate < 8000 or sample_rate > 48000:
        return None, response(400, {"error": "invalid_sample_rate"})

    session = get_session(session_id)
    if not session:
        session = create_session({"session_id": session_id, "visit_type": visit_type})

    # Amazon Transcribe Streaming의 session-id는 UUID 형식만 허용한다.
    # 서비스의 문진 session_id는 `s_...` 형태라 그대로 넘기면 WebSocket이
    # 열리자마자 ValidationException으로 종료되므로, 스트리밍 연결마다
    # AWS 규격에 맞는 별도 UUID를 발급한다. 이 값은 저장 식별자가 아니라
    # Transcribe 연결 추적용 임시 ID다.
    stream_session_id = str(uuid.uuid4())
    params = {
        "language-code": "ko-KR",
        "media-encoding": "pcm",
        "sample-rate": str(sample_rate),
        "session-id": stream_session_id,
    }
    vocabulary_name = configured_custom_vocabulary()
    if vocabulary_name:
        params["vocabulary-name"] = vocabulary_name

    url = (
        f"https://transcribestreaming.{REGION}.amazonaws.com:8443"
        f"/stream-transcription-websocket?{urlencode(params)}"
    )
    credentials = boto3.Session().get_credentials().get_frozen_credentials()
    request = AWSRequest(method="GET", url=url)
    SigV4QueryAuth(credentials, "transcribe", REGION, expires=300).add_auth(request)
    stream_url = request.url.replace("https://", "wss://", 1)

    streaming = session.get("streaming_stt", {})
    streaming[question_id] = {
        "provider": "amazon_transcribe_streaming",
        "language_code": "ko-KR",
        "sample_rate": sample_rate,
        "media_encoding": "pcm",
        "audio_stored": False,
    }
    update_session(session_id, {"streaming_stt": streaming, "status": "in_progress"})

    return {
        "stream_url": stream_url,
        "sample_rate": sample_rate,
        "media_encoding": "pcm",
        "language_code": "ko-KR",
        "audio_stored": False,
        "expires_in": 300,
    }, None
