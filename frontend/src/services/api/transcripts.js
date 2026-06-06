import { API_BASE_URL, ensureApiConfigured, sleep, useMockApi } from './client.js'
import { mockProcessResponse } from './mockResponses.js'

// Patient audio must not be stored in S3. These legacy helpers are kept only so
// old imports fail clearly instead of silently uploading protected voice data.
export async function uploadAudio() {
  throw new Error('audio_storage_disabled')
}

export async function getTranscript() {
  throw new Error('batch_transcribe_disabled')
}

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
  if (useMockApi()) {
    await sleep(600)
    return mockProcessResponse(questionType, visitType, transcript)
  }
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
