import {
  API_BASE_URL,
  apiHeaders,
  ensureApiConfigured,
  normalizeSession,
  rememberPatientToken,
} from './client.js'

// 접수처에서 환자 기본 정보를 받아 DynamoDB 세션을 생성합니다.
// 응답에는 직원 화면에서만 필요한 환자 태블릿 접근 토큰이 포함됩니다.
export async function createIntakeSession(form) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions`, {
    method: 'POST',
    headers: await apiHeaders({ role: 'staff', json: true }),
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
  const session = normalizeSession(await res.json())
  rememberPatientToken(session.sessionId, session.patientToken)
  return session
}

// 접수처에서 잘못 만든 문진 세션을 삭제합니다.
// 직원 화면의 대기열에서만 사용하는 API이며, 환자/의료진 화면에서는 호출하지 않습니다.
export async function deleteIntakeSession(sessionId) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: await apiHeaders({ role: 'staff' }),
  })
  if (!res.ok) throw new Error('문진 세션 삭제 실패')
  return res.json()
}

// 직원 대리 입력 중 문진 유형처럼 세션 메타데이터를 수정합니다.
// 환자가 직접 쓰는 API가 아니므로 직원 권한 토큰이 있을 때만 호출됩니다.
export async function updateIntakeSession(sessionId, updates) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PATCH',
    headers: await apiHeaders({ role: 'staff', json: true }),
    body: JSON.stringify(updates || {}),
  })
  if (!res.ok) throw new Error('문진 세션 수정 실패')
  const session = normalizeSession(await res.json())
  rememberPatientToken(session.sessionId, session.patientToken)
  return session
}

// 직원/의료진 대기열을 조회합니다.
// 직원 화면은 환자 태블릿 URL 생성이 필요하므로 환자 토큰을 포함해 받습니다.
export async function getDoctorQueue({ role = 'doctor' } = {}) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/doctor/queue`, {
    headers: await apiHeaders({ role }),
  })
  if (!res.ok) throw new Error('의사 대기열 조회 실패')
  const data = await res.json()
  const sessions = (data.sessions || []).map(normalizeSession)
  sessions.forEach((session) => rememberPatientToken(session.sessionId, session.patientToken))
  return sessions
}

// 특정 sessionId의 세션 상세를 조회합니다.
// 환자 화면에서는 URL/세션 저장소의 환자 토큰, 직원/의료진 화면에서는 역할 접근 코드를 사용합니다.
export async function getIntakeSession(sessionId, { role = '', patientToken = '' } = {}) {
  if (!sessionId) return null
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}`, {
    headers: await apiHeaders({ role, sessionId, patientToken }),
  })
  if (!res.ok) return null
  const session = normalizeSession(await res.json())
  rememberPatientToken(session.sessionId, session.patientToken)
  return session
}

// 환자가 태블릿에서 직원 도움을 요청하거나 안전 플래그로 멈춘 상태를 저장합니다.
export async function requestStaffHelp(sessionId) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/staff-help`, {
    method: 'POST',
    headers: await apiHeaders({ sessionId }),
  })
  if (!res.ok) return null
  return normalizeSession(await res.json())
}

export async function recordPatientConsent(sessionId, consent) {
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/consent`, {
    method: 'POST',
    headers: await apiHeaders({ sessionId, json: true }),
    body: JSON.stringify(consent),
  })
  if (!res.ok) throw new Error('개인정보 동의 이력 저장 실패')
  return normalizeSession(await res.json())
}
