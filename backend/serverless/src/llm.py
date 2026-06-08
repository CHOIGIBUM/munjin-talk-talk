"""Bedrock JSON-call helpers.

Nova Pro/Lite prompt는 각 업무 모듈에서 만들고, 실제 Bedrock converse 호출과
JSON 추출은 이 모듈을 통과합니다. 응답이 markdown fence를 포함해도 JSON만
꺼내도록 방어합니다.
"""

import json
import re

from langchain_prompting import build_bedrock_messages
from settings import bedrock_runtime

def call_bedrock_json(prompt, model_id, max_tokens):
    """Bedrock converse를 호출하고 첫 번째 JSON object만 dict로 파싱합니다."""
    resp = bedrock_runtime.converse(
        modelId=model_id,
        messages=build_bedrock_messages(prompt),
        inferenceConfig={"temperature": 0, "maxTokens": max_tokens},
    )
    raw_text = "".join(
        block.get("text", "")
        for block in resp.get("output", {}).get("message", {}).get("content", [])
    )
    return extract_first_json_object(raw_text), raw_text


def extract_first_json_object(text):
    """LLM 응답 텍스트에서 가장 바깥 JSON object를 찾아 파싱합니다."""
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
