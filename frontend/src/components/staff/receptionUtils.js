// 접수처 화면에서 공유하는 기본값과 표시 유틸입니다.
// UI 컴포넌트가 "상태값의 의미"나 "연락처 포맷"을 직접 알지 않도록 분리했습니다.

export const INITIAL_RECEPTION_FORM = {
  fullName: '최영자',
  birthDate: '1950-09-17',
  gender: '여성',
  receiptId: '',
  department: '이비인후과',
  doctor: '이민우',
  phone: '',
  visitType: 'initial',
}

export const SESSION_STATUS_LABEL = {
  waiting_tablet: '문진 대기',
  in_progress: '문진 진행중',
  staff_help: '직원 도움 요청',
  completed: '의사 답변 대기',
  needs_priority: '우선 확인 필요',
  reviewed: '답변·안내 완료',
}

export const MANUAL_INPUT_STATUSES = new Set(['staff_help', 'needs_priority', 'in_progress', 'waiting_tablet'])

export function formatPhone(value) {
  const digits = String(value || '').replace(/\D/g, '').slice(0, 11)
  if (digits.length <= 3) return digits
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`
}
