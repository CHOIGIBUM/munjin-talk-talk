// API 공통 설정과 응답 정규화 유틸입니다.
// 운영 배포에서는 VITE_API_BASE_URL이 API Gateway 주소를 반드시 가리켜야 합니다.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export function isRemoteApiEnabled() {
  return Boolean(API_BASE_URL)
}

export function ensureApiConfigured() {
  if (!API_BASE_URL) {
    throw new Error('API endpoint is not configured.')
  }
}

// Lambda 응답의 snake_case 필드를 화면이 쓰는 camelCase 필드와 함께 읽을 수 있게 맞춥니다.
export function normalizeSession(session) {
  if (!session) return null
  const patient = session.patient || {}
  return {
    ...session,
    sessionId: session.sessionId || session.session_id,
    queueNumber: Number(session.queueNumber || session.queue_number || 0),
    visitType: session.visitType || session.visit_type || 'initial',
    questionSetId: session.questionSetId || session.question_set_id || 'default',
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
