// 백엔드 LLM prompt에 전달할 순수 질문 문구입니다.
// badge, sub, example은 화면 안내용이므로 prompt 오염을 막기 위해 제외합니다.
export function questionTextForBackend(question) {
  if (!question) return ''
  return String(question.prompt_text || question.title || '')
    .replace(/\s+/g, ' ')
    .trim()
}
