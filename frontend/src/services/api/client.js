// API 공통 설정과 응답 정규화 유틸입니다.
// 배포 환경에서는 VITE_API_BASE_URL이 Lambda/API Gateway 주소를 가리키고,
// 로컬 목업 시연에서는 VITE_ENABLE_MOCKS=true일 때 demoSessions를 사용합니다.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
export const ENABLE_MOCKS = import.meta.env.VITE_ENABLE_MOCKS === 'true'

// 백엔드 주소가 비어 있고 명시적으로 목업을 켠 경우에만 목업 API를 사용합니다.
export function useMockApi() {
  return !API_BASE_URL && ENABLE_MOCKS
}

export function isMockApiEnabled() {
  return useMockApi()
}

export function isRemoteApiEnabled() {
  return Boolean(API_BASE_URL)
}

export function ensureApiConfigured() {
  if (!API_BASE_URL) {
    throw new Error('API endpoint is not configured.')
  }
}

// Lambda 응답과 로컬 목업 응답의 key 이름이 조금 달라도
// UI 컴포넌트가 항상 같은 shape으로 읽도록 맞춰줍니다.
export function normalizeSession(session) {
  if (!session) return null
  const patient = session.patient || {}
  return {
    ...session,
    sessionId: session.sessionId || session.session_id,
    queueNumber: Number(session.queueNumber || session.queue_number || 0),
    visitType: session.visitType || session.visit_type || 'initial',
    patient: {
      ...patient,
      fullName: patient.fullName || patient.full_name || '',
      birthDate: patient.birthDate || patient.birth_date || '',
      receiptId: patient.receiptId || patient.receipt_id || '',
      name: patient.name || '환자',
      gender: patient.gender || '-',
      department: patient.department || '이비인후과',
      doctor: patient.doctor || '',
      honorific: patient.honorific || '어르신',
    },
  }
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
