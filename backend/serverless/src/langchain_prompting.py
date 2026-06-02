"""LangChain prompt/message adapter for Bedrock calls.

문진톡톡은 Bedrock 자체 SDK로 Nova 모델을 호출하지만, LLM 입력을 조립하는
계층은 LangChain Core의 `ChatPromptTemplate`을 사용합니다. 이렇게 두면
나중에 RAG retriever, output parser, runnable chain을 추가할 때도 같은
프롬프트 계층을 확장할 수 있습니다.
"""

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate


def build_bedrock_messages(prompt: str):
    """LangChain ChatPromptTemplate으로 Bedrock Converse 메시지를 생성합니다.

    현재는 기존 프롬프트 내용을 바꾸지 않기 위해 human message 1개만 만듭니다.
    즉, 모델 동작은 기존과 최대한 동일하게 유지하면서 LangChain prompt/message
    abstraction을 실제 호출 경로에 넣는 역할입니다.
    """
    chat_prompt = ChatPromptTemplate.from_messages([("human", "{prompt}")])
    prompt_value = chat_prompt.invoke({"prompt": prompt or ""})
    return [_to_bedrock_message(message) for message in prompt_value.to_messages()]


def _to_bedrock_message(message):
    """LangChain message 객체를 Bedrock Converse message 형식으로 변환합니다."""
    role = "user" if isinstance(message, HumanMessage) else "assistant"
    return {"role": role, "content": [{"text": _message_text(message.content)}]}


def _message_text(content):
    """LangChain message content가 list/dict로 들어와도 안전하게 문자열화합니다."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content or "")
