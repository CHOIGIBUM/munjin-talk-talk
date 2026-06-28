// API 공통 설정과 인증 헤더 조립을 담당합니다.
// 직원/의료진은 접근 코드를 직접 API에 반복 전송하지 않고,
// 백엔드가 발급한 짧은 시간 유효 세션 토큰만 Authorization 헤더에 싣습니다.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const ROLE_SESSION_STORAGE = {
  staff: 'munjin:staff-role-session',
  doctor: 'munjin:doctor-role-session',
}

let authPromptHandler = null
const pendingAuthRequests = []
let activeAuthPrompt = null

function normalizeHonorific(value) {
  const honorific = String(value || '').trim()
  if (!honorific || honorific === '어르신') return '환자님'
  return honorific
}

export function isRemoteApiEnabled() {
  return Boolean(API_BASE_URL)
}

export function ensureApiConfigured() {
  if (!API_BASE_URL) {
    throw new Error('API endpoint is not configured.')
  }
}

export function setAuthPromptHandler(handler) {
  authPromptHandler = handler
  if (!authPromptHandler) return
  const pending = pendingAuthRequests.splice(0)
  pending.forEach(({ role, resolve, reject }) => {
    requestRoleSession(role).then(resolve).catch(reject)
  })
}

// Lambda 응답의 snake_case 필드를 화면에서 쓰는 camelCase 필드와 함께 맞춥니다.
export function normalizeSession(session) {
  if (!session) return null
  const patient = session.patient || {}
  return {
    ...session,
    sessionId: session.sessionId || session.session_id,
    queueNumber: Number(session.queueNumber || session.queue_number || 0),
    doctorQueuePosition: Number(session.doctorQueuePosition || session.doctor_queue_position || 0),
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
      honorific: normalizeHonorific(patient.honorific),
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

function roleSessionStorageKey(role) {
  return ROLE_SESSION_STORAGE[role] || ''
}

function readRoleSession(role) {
  const key = roleSessionStorageKey(role)
  if (!key) return null
  try {
    return JSON.parse(window.sessionStorage.getItem(key) || 'null')
  } catch {
    window.sessionStorage.removeItem(key)
    return null
  }
}

function writeRoleSession(role, session) {
  const key = roleSessionStorageKey(role)
  if (!key || !session?.access_token) return
  window.sessionStorage.setItem(key, JSON.stringify(session))
}

function isRoleSessionValid(session) {
  if (!session?.access_token || !session?.expires_at) return false
  const expiresAt = new Date(session.expires_at).getTime()
  return Number.isFinite(expiresAt) && expiresAt > Date.now() + 30_000
}

export async function loginWithAccessCode(role, accessCode) {
  ensureApiConfigured()
  const res = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      role,
      access_code: accessCode,
    }),
  })
  const payload = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(payload?.message || '접근 코드가 맞지 않습니다.')
  }
  writeRoleSession(role, payload)
  return payload
}

async function roleSessionToken(role) {
  if (!role) return ''
  const cached = readRoleSession(role)
  if (isRoleSessionValid(cached)) return cached.access_token

  const session = await requestRoleSession(role)
  if (!isRoleSessionValid(session)) {
    throw new Error('접속 시간이 만료되었습니다. 다시 로그인해 주세요.')
  }
  return session.access_token
}

function requestRoleSession(role) {
  if (activeAuthPrompt?.role === role) return activeAuthPrompt.promise
  if (activeAuthPrompt) {
    return activeAuthPrompt.promise.finally(() => requestRoleSession(role))
  }

  if (authPromptHandler) {
    const promptPromise = authPromptHandler({ role }).finally(() => {
      if (activeAuthPrompt?.promise === promptPromise) activeAuthPrompt = null
    })
    activeAuthPrompt = { role, promise: promptPromise }
    return promptPromise
  }

  return new Promise((resolve, reject) => {
    pendingAuthRequests.push({ role, resolve, reject })
  })
}

export async function apiHeaders({ role = '', sessionId = '', patientToken = '', json = false } = {}) {
  const headers = {}
  if (json) headers['Content-Type'] = 'application/json'

  const roleToken = await roleSessionToken(role)
  if (roleToken) headers.Authorization = `Bearer ${roleToken}`

  const patient = patientToken || getPatientToken(sessionId)
  if (patient) headers['X-Munjin-Patient-Token'] = patient

  return headers
}
