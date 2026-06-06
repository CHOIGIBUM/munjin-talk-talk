"""Compatibility facade for the Lambda handler.

The backend used to keep almost every operation in this single file. The
implementation now lives in smaller modules by responsibility, while this file
keeps the original import surface stable for handler.py and old scripts.

즉, 새 로직은 여기에 추가하지 말고 각 역할 모듈에 추가합니다.
"""

from audio import generate_streaming_transcribe_url, generate_upload_url, get_or_start_transcript
from extraction import extract_question
from guide import get_guide, save_doctor_response
from onepager import build_onepager, validate_and_save
from orchestration import process_answer
from retrieval import match_slots
from sessions import create_session, get_session, list_sessions, public_session, update_session
from utils import parse_body, response

__all__ = [
    "build_onepager",
    "create_session",
    "extract_question",
    "generate_upload_url",
    "generate_streaming_transcribe_url",
    "get_guide",
    "get_or_start_transcript",
    "get_session",
    "list_sessions",
    "match_slots",
    "parse_body",
    "process_answer",
    "public_session",
    "response",
    "save_doctor_response",
    "update_session",
    "validate_and_save",
]
