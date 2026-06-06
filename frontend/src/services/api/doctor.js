import {
  getDemoGuide,
  getDemoOnePager,
  saveDoctorResponse,
} from '../demoSessions.js'
import { API_BASE_URL, ensureApiConfigured, useMockApi } from './client.js'
import { mockPatientGuide } from './mockResponses.js'

// 원페이퍼 JSON을 조회합니다.
// 백엔드는 validate 단계마다 onepager를 갱신하므로, 이 화면은 저장된 최신 결과를 읽습니다.
export async function getOnePager(sessionId) {
  if (!sessionId) return null
  if (useMockApi()) return getDemoOnePager(sessionId)
  if (!API_BASE_URL) return null

  const res = await fetch(`${API_BASE_URL}/onepager/${sessionId}`)
  if (!res.ok) return null
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
  if (useMockApi()) {
    await new Promise((resolve) => setTimeout(resolve, 1000))
    saveDoctorResponse(sessionId, {
      reviewerId,
      answers,
      additionalNotes,
      savedAt: new Date().toISOString(),
    })
    return {
      doctor_review_saved: true,
      patient_guide_generated: true,
      validator_passed: true,
      patient_guide: mockPatientGuide(answers),
    }
  }
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
  if (useMockApi()) return getDemoGuide(sessionId)
  if (!API_BASE_URL) return null

  const res = await fetch(`${API_BASE_URL}/guide/${sessionId}`)
  if (!res.ok) return null
  return res.json()
}
