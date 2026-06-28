import { API_BASE_URL, apiHeaders, ensureApiConfigured } from './client.js'

// 환자가 Q1~Q4를 모두 확인한 뒤 호출합니다.
// 이 API는 답변 저장과 백그라운드 분석 큐 등록만 담당하므로 LLM 분석 완료를 기다리지 않습니다.
export async function processTranscriptsBatch({
  sessionId,
  questionSetId = 'default',
  visitType,
  answers,
  role = '',
}) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/process-answers`, {
    method: 'POST',
    headers: await apiHeaders({ role, sessionId, json: true }),
    body: JSON.stringify({
      session_id: sessionId,
      question_set_id: questionSetId,
      visit_type: visitType,
      answers,
    }),
  })

  const payload = await res.json().catch(() => ({}))
  if (!res.ok) {
    const message = payload?.message || payload?.error || '문진 답변 저장에 실패했습니다.'
    const error = new Error(message)
    error.payload = payload
    throw error
  }

  // LLM/validator 실패는 환자 흐름을 막지 않습니다.
  // 의사 화면에서 분석 중, 분석 실패, 재분석 버튼으로 후속 처리를 담당합니다.
  return payload
}
