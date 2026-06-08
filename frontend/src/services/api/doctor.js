import { API_BASE_URL, ensureApiConfigured } from './client.js'

// 원페이퍼 JSON을 조회합니다.
// 백엔드는 validate 단계마다 onepager를 갱신하므로, 이 화면은 저장된 최신 결과를 읽습니다.
export async function getOnePager(sessionId) {
  if (!sessionId) return null
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/onepager/${sessionId}`)
  if (!res.ok) return null
  return res.json()
}

// 저장된 onepaper를 기준으로 최종 AI 검토만 다시 실행합니다.
// 환자 답변 추출/IR을 다시 돌리는 것이 아니라 의료진 확인 항목과 EMR 초안을 재검토합니다.
export async function rerunOnePagerReview(sessionId) {
  if (!sessionId) return null
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/onepager/${sessionId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) throw new Error('원페이퍼 AI 재검토 실패')
  return res.json()
}

// 의사가 환자 질문에 답변하고 강조사항을 적으면 백엔드에 저장합니다.
// 백엔드는 이 값을 바탕으로 환자 안내문을 생성하거나, 의사 원문 강조사항을 그대로 노출합니다.
export async function submitDoctorResponse({
  sessionId,
  reviewerId,
  answers,
  additionalNotes,
}) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/doctor-response`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      reviewer_id: reviewerId || 'unknown',
      answers,
      patient_instruction: additionalNotes || '',
      additional_notes: additionalNotes || '',
    }),
  })
  if (!res.ok) throw new Error('의사 답변 저장 실패')
  return res.json()
}

// 진료 후 환자에게 보여줄 안내문 JSON을 조회합니다.
export async function getPatientGuide(sessionId) {
  if (!sessionId) return null
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/guide/${sessionId}`)
  if (!res.ok) return null
  return res.json()
}
