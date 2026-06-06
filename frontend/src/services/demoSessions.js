// 로컬 목업 모드 전용 세션 저장소입니다.
// 운영 배포에서는 DynamoDB가 세션 저장소이고, 이 파일은 VITE_ENABLE_MOCKS=true일 때만 쓰입니다.
const STORAGE_KEY = 'munjin_demo_sessions_v1'

const nowIso = () => new Date().toISOString()

const DEMO_SESSIONS = [
  {
    sessionId: 's-demo-a0427',
    queueNumber: 12,
    status: 'completed',
    visitType: 'initial',
    risk: 'none',
    patient: {
      name: '김*자',
      fullName: '김갑자',
      honorific: '어르신',
      birthDate: '1952-03-14',
      age: 74,
      gender: '여성',
      receiptId: 'A-0427',
      department: '이비인후과',
      doctor: '이민우',
      phone: '010-****-1212',
    },
    responses: {
      Q1: { text: '어제부터 목이 칼칼하고 코가 맥혀요. 기침도 조금 나요.' },
      Q2: { text: '그저께 저녁부터요. 손주 보러 갔다가 좀 추웠던 것 같아요.' },
      Q3: { text: '혈압약을 매일 아침에 먹어요. 다른 약은 안 먹고요.' },
      Q4: { text: '혈압약이랑 감기약을 같이 먹어도 되는지 궁금해요. 양파즙도 같이 먹어도 되나요?' },
    },
  },
  {
    sessionId: 's-demo-b0311',
    queueNumber: 13,
    status: 'needs_priority',
    visitType: 'followup',
    risk: 'high',
    patient: {
      name: '박*순',
      fullName: '박영순',
      honorific: '어르신',
      birthDate: '1948-10-03',
      age: 78,
      gender: '여성',
      receiptId: 'B-0311',
      department: '이비인후과',
      doctor: '이민우',
      phone: '010-****-4433',
    },
    responses: {
      Q1: { text: '약 먹고 목은 좀 나아졌는데 기침은 더 심해졌어요.' },
      Q2: { text: '잘 먹었는데 한 번씩 깜빡해서 저녁에 못 먹기도 했어요.' },
      Q3: { text: '어제는 가래에 피가 살짝 묻어 나왔어요.' },
      Q4: { text: '이 약을 언제까지 먹어야 되나요?' },
    },
  },
  {
    sessionId: 's-demo-c0188',
    queueNumber: 14,
    status: 'waiting_tablet',
    visitType: 'initial',
    risk: 'none',
    patient: {
      name: '이*호',
      fullName: '이성호',
      honorific: '어르신',
      birthDate: '1963-05-28',
      age: 63,
      gender: '남성',
      receiptId: 'C-0188',
      department: '이비인후과',
      doctor: '이민우',
      phone: '010-****-7788',
    },
    responses: {},
  },
]

export function listDemoSessions() {
  const stored = readSessions()
  return stored.sort((a, b) => (a.queueNumber || 0) - (b.queueNumber || 0))
}

export function getDemoSession(sessionId) {
  return listDemoSessions().find((session) => session.sessionId === sessionId) || null
}

// 접수처 목업 세션을 생성하고 localStorage에 저장합니다.
export function createDemoSession(input) {
  const sessions = readSessions()
  const queueNumber = Math.max(10, ...sessions.map((s) => Number(s.queueNumber) || 0)) + 1
  const sessionId = `s-demo-${Date.now().toString(36)}`
  const age = calculateAge(input.birthDate)
  const patient = {
    name: maskName(input.fullName || '환자'),
    fullName: input.fullName || '',
    honorific: '어르신',
    birthDate: input.birthDate || '',
    age,
    gender: input.gender || '-',
    receiptId: input.receiptId || `R-${String(queueNumber).padStart(4, '0')}`,
    department: input.department || '이비인후과',
    doctor: input.doctor || '이민우',
    phone: input.phone || '',
  }
  const next = {
    sessionId,
    queueNumber,
    status: 'waiting_tablet',
    visitType: input.visitType || 'initial',
    risk: 'none',
    patient,
    responses: {},
    createdAt: nowIso(),
    updatedAt: nowIso(),
  }
  writeSessions([next, ...sessions])
  return next
}

export function updateDemoSession(sessionId, patch) {
  const sessions = readSessions()
  const updated = sessions.map((session) => (
    session.sessionId === sessionId
      ? { ...session, ...patch, updatedAt: nowIso() }
      : session
  ))
  writeSessions(updated)
  return updated.find((session) => session.sessionId === sessionId) || null
}

// 태블릿에서 확정한 답변을 목업 세션 responses에 저장합니다.
export function saveTranscriptAnswer(sessionId, answer) {
  const session = getDemoSession(sessionId)
  if (!session) return null
  const responses = {
    ...(session.responses || {}),
    [answer.questionId]: {
      text: answer.transcript,
      result: answer.result,
      confirmedAt: nowIso(),
    },
  }
  return updateDemoSession(sessionId, {
    responses,
    status: 'in_progress',
    risk: answer.result?.safety_flag?.severity === 'high' ? 'high' : session.risk,
  })
}

export function markSessionCompleted(sessionId) {
  const session = getDemoSession(sessionId)
  if (!session) return null
  return updateDemoSession(sessionId, {
    status: session.risk === 'high' ? 'needs_priority' : 'completed',
    completedAt: nowIso(),
  })
}

export function markStaffRequested(sessionId) {
  return updateDemoSession(sessionId, {
    status: 'staff_help',
    staffHelpRequestedAt: nowIso(),
  })
}

export function saveDoctorResponse(sessionId, payload) {
  return updateDemoSession(sessionId, {
    status: 'reviewed',
    doctorResponse: payload,
    guideReady: true,
  })
}

// 목업 원페이퍼 JSON을 실제 백엔드 응답과 비슷한 구조로 만들어 UI 테스트에 사용합니다.
export function getDemoOnePager(sessionId) {
  const session = getDemoSession(sessionId)
  if (!session) return null
  const patient = session.patient || {}
  const followup = session.visitType === 'followup'
  const highRisk = session.risk === 'high'
  const responses = withDefaultResponses(session)

  const symptomSlots = followup
    ? [
        { name: '기침', source_question: 'Q1', source_quote: '기침은 더 심해졌어요', normalized_text: '기침이 악화됨', status: '있음', score: 0.89, alert: highRisk },
        ...(highRisk ? [{ name: '객혈', source_question: 'Q3', source_quote: '가래에 피가 살짝 묻어 나왔어요', normalized_text: '객혈 의심 표현', status: '있음', score: 0.93, alert: true }] : []),
      ]
    : [
        { name: '목 불편감', source_question: 'Q1', source_quote: '목이 칼칼하고', normalized_text: '목 불편감 호소', status: '있음', score: 0.91, alert: false },
        { name: '코막힘', source_question: 'Q1', source_quote: '코가 맥혀요', normalized_text: '코막힘 호소', status: '있음', score: 0.88, alert: false },
        { name: '기침', source_question: 'Q1', source_quote: '기침도 조금 나요', normalized_text: '기침 동반', status: '있음', score: 0.84, alert: false },
      ]

  const clinicalClues = followup
    ? [
        { id: 'c1', category: '재진경과', label: '악화', summary: '기침 악화', source_question: 'Q1', source_quote: '기침은 더 심해졌어요', priority: highRisk ? '우선' : '일반', related_symptoms: ['기침'] },
        { id: 'c2', category: '복약순응도', label: '누락', summary: '저녁 복약을 간헐적으로 빠뜨림', source_question: 'Q2', source_quote: '저녁에 못 먹기도 했어요', priority: '일반', related_symptoms: [] },
        ...(highRisk ? [{ id: 'c3', category: '재진경과', label: '새 증상', summary: '객혈 새로 발생', source_question: 'Q3', source_quote: '피가 살짝 묻어 나왔어요', priority: '우선', related_symptoms: ['객혈'] }] : []),
      ]
    : [
        { id: 'c1', category: '증상맥락', label: '시작시점', summary: '어제부터', source_question: 'Q1', source_quote: '어제부터', priority: '일반', related_symptoms: ['목 불편감', '코막힘', '기침'] },
        { id: 'c2', category: '증상맥락', label: '악화요인', summary: '추위 노출 후 시작된 듯함', source_question: 'Q2', source_quote: '좀 추웠던 것 같아요', priority: '일반', related_symptoms: [] },
        { id: 'c3', category: '복약정보', label: '복용중', summary: '혈압약 매일 아침 복용', source_question: 'Q3', source_quote: '혈압약을 매일 아침에 먹어요', priority: '일반', related_symptoms: [] },
      ]

  const agenda = followup
    ? [{ type: 'treatment_duration', category: 'treatment_duration', type_label: '복약 기간', summary: '복약 기간 문의', original_quote: responses.Q4.text, source_question: 'Q4' }]
    : [
        { type: 'drug_drug_interaction', category: 'drug_drug_interaction', type_label: '복약 상호작용', summary: '혈압약-감기약 병용 가능 여부 문의', original_quote: '혈압약이랑 감기약을 같이 먹어도 되는지 궁금해요', source_question: 'Q4' },
        { type: 'food_drug_interaction', category: 'food_drug_interaction', type_label: '음식-약 상호작용', summary: '양파즙 병용 가능 여부 문의', original_quote: '양파즙도 같이 먹어도 되나요?', source_question: 'Q4' },
      ]

  const safetyFlags = highRisk
    ? [{ category: 'hemoptysis', label: '객혈 의증', severity: 'high', matched_pattern: '피가 살짝', message: '객혈 의심 표현이 있어 우선 평가가 필요합니다.' }]
    : []

  return {
    session: {
      session_id: session.sessionId,
      case_id: session.sessionId,
      visit_type: session.visitType,
      responses,
      onepager: {
        patient_summary: {
          display_name: patient.name || '환자',
          age_text: `${patient.age || '-'}세`,
          sex: patient.gender || '-',
          department: patient.department || '이비인후과',
          received_at: formatTime(session.createdAt),
          audio_duration_text: '58초',
          visit_type: session.visitType,
        },
        agenda,
        symptom_slots: symptomSlots,
        clinical_clues: clinicalClues,
        review_items: highRisk
          ? ['[우선] 객혈량과 시작 시점 확인', '[우선] 흉부 X-ray/객담 검사 고려', '기침 악화 패턴 평가', '복약 누락 영향 평가']
          : ['발열 여부와 실제 체온 확인', '가래 동반 여부와 색깔', '혈압약과 일반 감기약 병용 가능 여부 안내', '양파즙 병용 가능 여부 답변'],
        transfer_text: highRisk
          ? `${patient.age || '-'}세 ${patient.gender || ''} 재진 환자. 기침 악화 및 객혈 의심 표현. 복약 누락 일부 있음.`
          : `${patient.age || '-'}세 ${patient.gender || ''} 환자. 목 불편감, 코막힘, 기침 호소. 혈압약 복용 중이며 감기약 병용 가능 여부 문의.`,
        safety_flags: safetyFlags,
        unresolved_items: [],
      },
    },
  }
}

// 목업 환자 안내문 JSON입니다.
export function getDemoGuide(sessionId) {
  const session = getDemoSession(sessionId)
  const patient = session?.patient || DEMO_SESSIONS[0].patient
  const highRisk = session?.risk === 'high'
  return {
    patient_name_masked: patient.name,
    patient_guide: {
      generated_at: nowIso(),
      items: highRisk
        ? [
            {
              question: '가래에 피가 묻어 나온 점',
              answer_simple: [
                '오늘은 피가 섞인 가래를 먼저 확인해야 합니다.',
                '검사가 필요할 수 있으니 진료실 안내를 꼭 따라 주세요.',
                '피가 많아지거나 숨이 차면 바로 직원에게 말씀해 주세요.',
              ],
            },
            {
              question: '약을 언제까지 먹어야 하는지',
              answer_simple: [
                '오늘 진료 후 선생님이 약 기간을 다시 정해 드립니다.',
                '임의로 약을 중단하지 말고 안내받은 날짜까지 복용해 주세요.',
              ],
            },
          ]
        : [
            {
              question: '혈압약이랑 감기약 같이 먹어도 되는지',
              answer_simple: [
                '혈압약은 평소처럼 계속 드세요.',
                '감기약은 선생님이 확인한 약으로만 드시는 것이 안전합니다.',
                '약국에서는 혈압약을 먹고 있다고 꼭 말씀해 주세요.',
              ],
            },
            {
              question: '양파즙도 같이 먹어도 되는지',
              answer_simple: [
                '양파즙은 하루 한 잔 정도로 줄여 드세요.',
                '속이 불편하거나 어지러우면 중단하고 병원에 알려 주세요.',
              ],
            },
          ],
    },
    doctor_additional_notes: highRisk
      ? '객혈 양상 변화 시 즉시 재내원하도록 안내했습니다.'
      : '열이 나거나 증상이 5일 이상 지속되면 다시 방문해 주세요.',
  }
}

function readSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      const seeded = DEMO_SESSIONS.map((session, idx) => ({
        ...session,
        createdAt: new Date(Date.now() - (idx + 1) * 8 * 60 * 1000).toISOString(),
        updatedAt: nowIso(),
      }))
      writeSessions(seeded)
      return seeded
    }
    return JSON.parse(raw)
  } catch {
    return DEMO_SESSIONS
  }
}

function writeSessions(sessions) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
    window.dispatchEvent(new Event('munjin-demo-sessions'))
  } catch {
    // localStorage unavailable: keep UI alive with in-memory fallback only.
  }
}

function withDefaultResponses(session) {
  const initial = {
    Q1: { text: '어제부터 목이 칼칼하고 코가 맥혀요. 기침도 조금 나요.' },
    Q2: { text: '그저께 저녁부터요. 손주 보러 갔다가 좀 추웠던 것 같아요.' },
    Q3: { text: '혈압약을 매일 아침에 먹어요. 다른 약은 안 먹고요.' },
    Q4: { text: '혈압약이랑 감기약을 같이 먹어도 되는지 궁금해요. 양파즙도 같이 먹어도 되나요?' },
  }
  const followup = {
    Q1: { text: '약 먹고 목은 좀 나아졌는데 기침은 더 심해졌어요.' },
    Q2: { text: '잘 먹었는데 한 번씩 깜빡해서 저녁에 못 먹기도 했어요.' },
    Q3: { text: '어제는 가래에 피가 살짝 묻어 나왔어요.' },
    Q4: { text: '이 약을 언제까지 먹어야 되나요?' },
  }
  return { ...(session.visitType === 'followup' ? followup : initial), ...(session.responses || {}) }
}

function calculateAge(birthDate) {
  if (!birthDate) return ''
  const birth = new Date(birthDate)
  if (Number.isNaN(birth.getTime())) return ''
  const today = new Date()
  let age = today.getFullYear() - birth.getFullYear()
  const beforeBirthday = today.getMonth() < birth.getMonth()
    || (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate())
  if (beforeBirthday) age -= 1
  return age
}

function maskName(name) {
  const clean = String(name || '').trim()
  if (clean.length <= 1) return clean || '환자'
  return `${clean[0]}*${clean.slice(-1)}`
}

function formatTime(value) {
  const date = value ? new Date(value) : new Date()
  if (Number.isNaN(date.getTime())) return '--:--'
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}
