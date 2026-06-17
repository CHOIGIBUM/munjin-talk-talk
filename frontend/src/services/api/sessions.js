import { API_BASE_URL, ensureApiConfigured, normalizeSession } from './client.js'

// 접수처에서 환자 기본 정보를 받아 DynamoDB 세션을 생성합니다.
// 여기서 만든 sessionId가 태블릿, 원페이퍼, 안내문 화면의 공통 키가 됩니다.
export async function createIntakeSession(form) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      visit_type: form.visitType,
      question_set_id: form.questionSetId || 'default',
      patient: {
        full_name: form.fullName,
        birth_date: form.birthDate,
        gender: form.gender,
        receipt_id: form.receiptId,
        department: form.department,
        doctor: form.doctor,
        phone: form.phone,
      },
    }),
  })
  if (!res.ok) throw new Error('문진 세션 생성 실패')
  return normalizeSession(await res.json())
}

// 의사 대기열과 접수처의 오늘 접수 목록을 불러옵니다.
// 운영 환경에서는 백엔드가 DynamoDB의 최신 세션 상태를 반환합니다.
export async function getDoctorQueue() {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/doctor/queue`)
  if (!res.ok) throw new Error('의사 대기열 조회 실패')
  const data = await res.json()
  return (data.sessions || []).map(normalizeSession)
}

// 특정 sessionId의 전체 세션 상세를 조회합니다.
// 태블릿 화면 재접속, 직원 직접 입력, 원페이퍼 화면에서 공통으로 사용합니다.
export async function getIntakeSession(sessionId) {
  if (!sessionId) return null
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}`)
  if (!res.ok) return null
  return normalizeSession(await res.json())
}

// 환자가 태블릿에서 직원 도움을 요청했거나 safety alert로 멈춘 상태를 저장합니다.
export async function requestStaffHelp(sessionId) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/staff-help`, {
    method: 'POST',
  })
  if (!res.ok) return null
  return normalizeSession(await res.json())
}

export async function recordPatientConsent(sessionId, consent) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/consent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(consent),
  })
  if (!res.ok) throw new Error('개인정보 동의 이력 저장 실패')
  return normalizeSession(await res.json())
}
