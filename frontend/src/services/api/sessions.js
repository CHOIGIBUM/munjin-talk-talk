import {
  createDemoSession,
  getDemoSession,
  listDemoSessions,
  markStaffRequested,
} from '../demoSessions.js'
import { API_BASE_URL, ensureApiConfigured, normalizeSession, useMockApi } from './client.js'

// 구버전 단독 태블릿 데모에서 쓰던 간단 세션 생성기입니다.
// 접수처 흐름에서는 createIntakeSession이 실제 세션 생성을 담당합니다.
export function createSession() {
  const sessionId = `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  return { sessionId, startedAt: new Date().toISOString() }
}

// 접수처에서 환자 기본 정보를 받아 DynamoDB 세션을 생성합니다.
// 여기서 만든 sessionId가 태블릿, 원페이퍼, 안내문 화면의 공통 키가 됩니다.
export async function createIntakeSession(form) {
  if (useMockApi()) {
    return createDemoSession(form)
  }
  ensureApiConfigured()

  const res = await fetch(`${API_BASE_URL}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      visit_type: form.visitType,
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
  if (useMockApi()) {
    return listDemoSessions()
  }
  if (!API_BASE_URL) return []

  const res = await fetch(`${API_BASE_URL}/doctor/queue`)
  if (!res.ok) return []
  const data = await res.json()
  return (data.sessions || []).map(normalizeSession)
}

// 특정 sessionId의 전체 세션 상세를 조회합니다.
// 태블릿 화면 재접속, 직원 직접 입력, 원페이퍼 화면에서 공통으로 사용합니다.
export async function getIntakeSession(sessionId) {
  if (!sessionId) return null
  if (useMockApi()) return getDemoSession(sessionId)
  if (!API_BASE_URL) return null

  const res = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}`)
  if (!res.ok) return null
  return normalizeSession(await res.json())
}

// 환자가 태블릿에서 직원 도움을 요청했거나 safety alert로 멈춘 상태를 저장합니다.
export async function requestStaffHelp(sessionId) {
  if (useMockApi()) {
    return markStaffRequested(sessionId)
  }
  if (!API_BASE_URL) return null

  const res = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/staff-help`, {
    method: 'POST',
  })
  if (!res.ok) return null
  return normalizeSession(await res.json())
}
