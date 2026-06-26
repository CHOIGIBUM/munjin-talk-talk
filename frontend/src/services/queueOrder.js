const DOCTOR_QUEUE_PRIORITY = {
  needs_priority: 0,
  waiting_doctor: 1,
  completed: 1,
  analysis_failed: 2,
  analysis_pending: 3,
  in_progress: 4,
  staff_help: 5,
  consent_rejected: 5,
  waiting_tablet: 6,
  reviewed: 7,
}

function numericQueue(session) {
  const value = Number(session?.queueNumber || session?.queue_number || 0)
  return Number.isFinite(value) && value > 0 ? value : Number.MAX_SAFE_INTEGER
}

function createdTime(session) {
  const value = new Date(session?.createdAt || session?.created_at || 0).getTime()
  return Number.isFinite(value) ? value : 0
}

function tieBreak(a, b) {
  return String(a?.sessionId || a?.session_id || '').localeCompare(String(b?.sessionId || b?.session_id || ''))
}

export function compareByOriginalQueue(a, b) {
  const queueDiff = numericQueue(a) - numericQueue(b)
  if (queueDiff !== 0) return queueDiff
  const createdDiff = createdTime(a) - createdTime(b)
  if (createdDiff !== 0) return createdDiff
  return tieBreak(a, b)
}

export function sortDoctorQueue(sessions = []) {
  return [...sessions].sort((a, b) => {
    const priorityDiff = (DOCTOR_QUEUE_PRIORITY[a.status] ?? 9) - (DOCTOR_QUEUE_PRIORITY[b.status] ?? 9)
    if (priorityDiff !== 0) return priorityDiff
    return compareByOriginalQueue(a, b)
  })
}

export function sortTabletQueue(sessions = []) {
  return [...sessions].sort(compareByOriginalQueue)
}
