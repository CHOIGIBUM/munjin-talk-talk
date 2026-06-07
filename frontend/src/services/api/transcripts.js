import { API_BASE_URL, ensureApiConfigured } from './client.js'

// Submit the already-streamed transcript to the backend orchestration graph.
// The backend runs Bedrock extraction, schema validation, symptom IR, session
// save, and onepaper refresh in a single server-side pipeline.
export async function processTranscript({
  sessionId,
  questionId,
  questionType,
  visitType,
  transcript,
}) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/process-answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      question_id: questionId,
      question_type: questionType,
      visit_type: visitType,
      transcript,
    }),
  })

  const payload = await res.json().catch(() => ({}))
  if (!res.ok) {
    const message = payload?.message || payload?.error || '문진 처리에 실패했습니다'
    throw new Error(message)
  }
  if (payload.validator_passed === false) {
    throw new Error('문진 결과 검증에 실패했습니다. 다시 말씀해 주세요.')
  }
  return payload
}
