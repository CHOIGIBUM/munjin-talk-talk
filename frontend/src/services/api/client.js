// API 공통 설정과 인증 헤더 조립을 담당합니다.
// 직원/의료진 접근 코드는 프론트 빌드에 박지 않고, 브라우저 세션 탭 안에만 보관합니다.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const ROLE_TOKEN_STORAGE = {
  staff: 'munjin:staff-access-token',
  doctor: 'munjin:doctor-access-token',
}

export function isRemoteApiEnabled() {
  return Boolean(API_BASE_URL)
}

export function ensureApiConfigured() {
  if (!API_BASE_URL) {
    throw new Error('API endpoint is not configured.')
  }
}

// Lambda 응답의 snake_case 필드를 화면에서 쓰는 camelCase 필드와 함께 맞춥니다.
export function normalizeSession(session) {
  if (!session) return null
  const patient = session.patient || {}
  return {
    ...session,
    sessionId: session.sessionId || session.session_id,
    queueNumber: Number(session.queueNumber || session.queue_number || 0),
    visitType: session.visitType || session.visit_type || 'initial',
    questionSetId: session.questionSetId || session.question_set_id || 'default',
    patientToken: session.patientToken || session.patient_token || '',
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

function patientTokenStorageKey(sessionId) {
  return `munjin:patient-token:${sessionId}`
}

export function rememberPatientToken(sessionId, token) {
  if (!sessionId || !token) return
  window.sessionStorage.setItem(patientTokenStorageKey(sessionId), token)
}

export function getPatientToken(sessionId) {
  if (!sessionId) return ''
  const query = new URLSearchParams(window.location.search)
  const tokenFromUrl = query.get('pt') || query.get('patient_token') || ''
  if (tokenFromUrl) {
    rememberPatientToken(sessionId, tokenFromUrl)
    return tokenFromUrl
  }
  return window.sessionStorage.getItem(patientTokenStorageKey(sessionId)) || ''
}

export function sessionUrl(path, patientToken = '') {
  if (!patientToken) return path
  const joiner = path.includes('?') ? '&' : '?'
  return `${path}${joiner}pt=${encodeURIComponent(patientToken)}`
}

function roleToken(role) {
  if (!role) return ''
  const key = ROLE_TOKEN_STORAGE[role]
  if (!key) return ''

  const cached = window.sessionStorage.getItem(key)
  if (cached) return cached

  const label = role === 'doctor' ? '의료진 접근 코드' : '직원 접근 코드'
  const token = window.prompt(`${label}를 입력해 주세요.`) || ''
  if (token.trim()) window.sessionStorage.setItem(key, token.trim())
  return token.trim()
}

export function apiHeaders({ role = '', sessionId = '', patientToken = '', json = false } = {}) {
  const headers = {}
  if (json) headers['Content-Type'] = 'application/json'

  const access = roleToken(role)
  if (access) headers['X-Munjin-Access-Token'] = access

  const patient = patientToken || getPatientToken(sessionId)
  if (patient) headers['X-Munjin-Patient-Token'] = patient

  return headers
}
