// 백엔드 onepager JSON을 의사 UI가 기대하는 형태로 정규화하는 어댑터입니다.
// 백엔드 스키마가 조금 바뀌어도 화면 컴포넌트 수정 범위를 이 파일에 가두기 위한 층입니다.
const DEFAULT_PATIENT = {
  name: '환자',
  age: 0,
  gender: '-',
  department: '이비인후과',
  visit_type: 'initial',
  receivedAt: '--:--',
  audioDuration: 0,
}

export function normalizeOnePager(raw) {
  if (!raw) return null

  const current = normalizeCurrentBackend(raw)
  if (current) return current

  return null
}

// DoctorAgendaPanel은 Q4 환자 질문과 안내문 입력에 필요한 부분만 읽습니다.
// 전체 onepager를 몰라도 agenda 관련 필드만 안정적으로 꺼내기 위한 helper입니다.
export function normalizeAgendaSource(raw) {
  const normalized = normalizeOnePager(raw)
  return {
    agenda: normalized ? (normalized.agenda || []) : [],
    full_q4_transcript: normalized?.full_q4_transcript || '',
    uncategorized_remnant: normalized?.uncategorized_remnant || '',
  }
}

// 현재 MVP 백엔드가 저장하는 session.onepager 구조를 화면용 구조로 변환합니다.
function normalizeCurrentBackend(raw) {
  const session = raw.session || raw
  const onepager = session.onepager || raw.onepager
  if (!onepager) return null

  const visitType = normalizeVisitType(session.visit_type || raw.visit_type || onepager.patient_summary?.visit_type)
  const patient = normalizePatientSummary(onepager.patient_summary, visitType)
  const agenda = normalizeAgenda(onepager.agenda || [])
  const safetyFlags = Array.isArray(onepager.safety_flags) ? onepager.safety_flags : []
  const normalizedSafetyFlags = safetyFlags.map(normalizeSafetyFlag).filter(Boolean)
  const safetyFlag = normalizedSafetyFlags[0] || null
  const symptomSlots = mergeSafetyFlagsIntoSymptomSlots(
    normalizeSymptomSlots(onepager.symptom_slots || []),
    normalizedSafetyFlags
  )
  const clinicalClues = onepager.clinical_clues || []
  const doctorBrief = normalizeDoctorBrief(onepager.doctor_brief)
  const analysis = onepager.analysis || session.analysis || raw.analysis || {
    status: session.analysis_status || raw.analysis_status || '',
    error: session.analysis_error || raw.analysis_error || '',
  }

  return {
    status: session.status || raw.status || '',
    analysis,
    patient,
    agenda,
    full_q4_transcript: getResponseText(session.responses, 'Q4'),
    patientQuestionnaire: normalizePatientQuestionnaire(session.responses),
    uncategorized_remnant: (onepager.unresolved_items || []).map(x => x.display_text || x.normalized_text || x.source_quote).filter(Boolean).join(' / '),
    symptomSlots,
    clinicalClues,
    doctorBrief,
    reviewItems: normalizeReviewItems(onepager.review_items || [], onepager),
    transferText: normalizeTransferText(
      onepager.transfer_text || '',
      { ...onepager, symptom_slots: symptomSlots, agenda, clinical_clues: clinicalClues },
      patient
    ),
    safety_flag: safetyFlag,
    safety_flags: normalizedSafetyFlags,
    unresolvedItems: onepager.unresolved_items || [],
  }
}

// 원페이퍼 좌측 상단의 환자 표시용 필드를 안전한 기본값과 함께 만듭니다.
function normalizePatientSummary(summary, visitType) {
  return {
    ...DEFAULT_PATIENT,
    name: summary?.display_name || DEFAULT_PATIENT.name,
    age: parseInt(String(summary?.age_text || '').replace(/[^0-9]/g, ''), 10) || DEFAULT_PATIENT.age,
    gender: summary?.sex || DEFAULT_PATIENT.gender,
    department: summary?.department || DEFAULT_PATIENT.department,
    visit_type: visitType,
    receivedAt: summary?.received_at || DEFAULT_PATIENT.receivedAt,
    audioDuration: parseInt(String(summary?.audio_duration_text || '').replace(/[^0-9]/g, ''), 10) || DEFAULT_PATIENT.audioDuration,
  }
}

// Q4에서 분리된 환자 질문 목록을 의사 답변 패널이 쓰는 agenda 형태로 맞춥니다.
function normalizeAgenda(items) {
  return (items || []).map(item => ({
    type: item.type || item.category || 'other',
    category: item.category || item.type || 'other',
    type_label: item.type_label || item.title || categoryToKorean(item.category || item.type),
    summary: item.summary || item.display_text || '',
    original_quote: item.original_quote || item.source_quote || '',
    source_question: item.source_question || 'Q4',
  }))
}

// 증상 매칭 결과를 카드 UI에서 바로 렌더링할 수 있는 필드명으로 맞춥니다.
function normalizeSymptomSlots(slots) {
  return (slots || []).map(slot => ({
    name: slot.name || slot.display_text || '-',
    sub: slot.sub || slot.status || slot.source_question || '',
    sourceQuote: slot.sourceQuote || slot.source_quote || '',
    sourceQuestion: slot.sourceQuestion || slot.source_question || '',
    normalizedText: slot.normalized_text || '',
    status: slot.status || '',
    explain: slot.explain || '',
    alert: Boolean(slot.alert),
  }))
}

// rule-base 안전 플래그는 별도 경고 배너로만 보이면 의사가 증상 목록에서 놓칠 수 있습니다.
// 그래서 flag 표현을 "오늘 말한 불편함"에도 우선 확인 카드로 합칩니다.
function mergeSafetyFlagsIntoSymptomSlots(slots, flags) {
  const normalizedSlots = (slots || []).map(slot => {
    const matchedFlag = findMatchingSafetyFlag(slot, flags)
    if (!matchedFlag) return slot

    return {
      ...slot,
      sourceQuote: slot.sourceQuote || matchedFlag.matched_pattern || '',
      normalizedText: slot.normalizedText || matchedFlag.message || '',
      explain: slot.explain || matchedFlag.message || '문진 중 우선 확인이 필요한 표현으로 감지되었습니다.',
      alert: true,
    }
  })
  const flagSlots = (flags || [])
    .map(flag => safetyFlagToSymptomSlot(flag, normalizedSlots))
    .filter(Boolean)
  return [...normalizedSlots, ...flagSlots]
}

function findMatchingSafetyFlag(slot, flags) {
  return (flags || []).find(flag => {
    const flagQuote = flag.matched_pattern || ''
    const flagName = flag.label || flag.category || ''
    const sameQuote = flagQuote && slot.sourceQuote && slot.sourceQuote.includes(flagQuote)
    const sameName = flagName && slot.name && (slot.name === flagName || flagName.includes(slot.name) || slot.name.includes(flagName))
    return sameQuote || sameName
  })
}

function safetyFlagToSymptomSlot(flag, existingSlots) {
  const sourceQuote = flag.matched_pattern || ''
  const name = flag.label || flag.category || '우선 확인 필요'
  if (!sourceQuote && !name) return null

  const alreadyShown = (existingSlots || []).some(slot => findMatchingSafetyFlag(slot, [flag]))
  if (alreadyShown) return null

  return {
    name,
    sub: '있음',
    sourceQuote,
    sourceQuestion: flag.source_question || '',
    normalizedText: flag.message || '',
    status: '있음',
    explain: flag.message || '문진 중 우선 확인이 필요한 표현으로 감지되었습니다.',
    alert: true,
  }
}

function normalizeReviewItems(items, onepager = {}) {
  const normalized = (items || []).map(item => {
    if (typeof item === 'string') return item
    const text = item.text || item.summary || ''
    if (item.priority === '우선' && text && !text.startsWith('[우선]')) return `[우선] ${text}`
    return text
  }).filter(Boolean)
  return normalized.length ? normalized : buildFallbackReviewItems(onepager)
}

function buildFallbackReviewItems(onepager = {}) {
  const items = []
  const safetyFlags = Array.isArray(onepager.safety_flags) ? onepager.safety_flags : []
  const symptomSlots = Array.isArray(onepager.symptom_slots) ? onepager.symptom_slots : []
  const clinicalClues = Array.isArray(onepager.clinical_clues) ? onepager.clinical_clues : []
  const agenda = Array.isArray(onepager.agenda) ? onepager.agenda : []

  safetyFlags.forEach(flag => {
    const label = cleanText(flag.label || flag.category || flag.matched_pattern || '우선 확인 표현')
    if (label) items.push(`[우선] ${label} 관련 위험 신호와 우선 진료 필요성 확인`)
  })
  symptomSlots.forEach(slot => {
    const name = cleanText(slot.name || slot.display_text || slot.normalized_text)
    if (name) items.push(`${name}의 지속 시간, 악화 정도, 동반 증상 확인`)
  })
  clinicalClues.forEach(clue => {
    const hint = cleanText(clue.action_hint || clue.summary || clue.source_quote)
    if (hint) items.push(hint.endsWith('확인') ? hint : `${hint} 확인`)
  })
  agenda.forEach(item => {
    const question = cleanText(item.summary || item.original_quote || item.display_text)
    if (question) items.push(`환자 질문 답변: ${question}`)
  })

  return uniqueTexts(items).slice(0, 6)
}

function cleanText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function uniqueTexts(items) {
  const seen = new Set()
  return items.filter(item => {
    const key = cleanText(item)
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function normalizeTransferText(text, onepager = {}, patient = DEFAULT_PATIENT) {
  const cleaned = cleanText(text)
  if (cleaned && isChartLikeTransferText(cleaned)) return cleaned
  return buildChartTransferText(onepager, patient)
}

function isChartLikeTransferText(text) {
  if (/환자는|언급했습니다|궁금합니다|필요합니다/.test(text)) return false
  if (/\bO\s*[:)]|객관소견/i.test(text)) return false
  return /S\)|CC\s*:/.test(text)
}

function buildChartTransferText(onepager = {}, patient = DEFAULT_PATIENT) {
  const visitLabel = patient.visit_type === 'followup' ? '재진' : '초진'
  const demographics = `${patient.age || '-'}세 ${patient.gender || ''} ${visitLabel}`.replace(/\s+/g, ' ').trim()
  const symptomSlots = Array.isArray(onepager.symptom_slots) ? onepager.symptom_slots : []
  const clinicalClues = Array.isArray(onepager.clinical_clues) ? onepager.clinical_clues : []
  const agenda = Array.isArray(onepager.agenda) ? onepager.agenda : []
  const symptoms = uniqueTexts(symptomSlots.map(slot => cleanText(slot.name || slot.display_text || slot.normalized_text))).join(', ')
  const contexts = uniqueTexts(clinicalClues.map(clue => cleanText(clue.summary || clue.source_quote)))
  const medContexts = contexts.filter(text => /약|복용|병용|처방/.test(text))
  const piContexts = contexts.filter(text => !medContexts.includes(text))
  const questions = uniqueTexts(agenda.map(item => cleanText(item.summary || item.original_quote || item.originalQuote || item.display_text)))

  const parts = [`S) ${demographics}`]
  if (symptoms) parts.push(`CC: ${symptoms}`)
  if (piContexts.length) parts.push(`PI: ${piContexts.slice(0, 2).join('; ')}`)
  if (medContexts.length) parts.push(`Med: ${medContexts.slice(0, 2).join('; ')}`)
  if (questions.length) parts.push(`Q: ${questions.slice(0, 2).join('; ')}`)

  const checks = []
  if (symptoms) checks.push('증상 지속시간/중증도')
  if (medContexts.length || questions.length) checks.push('복약/병용 가능 여부')
  if (!checks.length) checks.push('문진 내용')
  parts.push(`확인: ${uniqueTexts(checks).join(', ')}`)

  return parts.join(' / ')
}

function normalizeDoctorBrief(brief) {
  if (brief?.sections?.length || brief?.headline) {
    return {
      headline: brief.headline || '',
      priority: brief.priority || '일반',
      sections: (brief.sections || []).map(normalizeBriefSection).filter(Boolean),
    }
  }

  return { headline: '', priority: '일반', sections: [] }
}

function normalizeBriefSection(section) {
  if (!section) return null
  return {
    key: section.key || section.title || 'section',
    title: section.title || '문진 맥락',
    priority: section.priority || '일반',
    summary: section.summary || '',
    items: (section.items || []).map(item => ({
      text: item.text || item.summary || '',
      source_question: item.source_question || '',
      source_quote: item.source_quote || item.original_quote || '',
    })).filter(item => item.text),
  }
}

function normalizeSafetyFlag(flag) {
  if (!flag) return null
  return {
    category: flag.category || flag.type || 'safety',
    label: flag.label || flag.type || '우선 확인',
    severity: flag.severity || (flag.level === '의료진우선확인' ? 'high' : 'medium'),
    matched_pattern: flag.matched_pattern || flag.source_quote || '',
    message: flag.message || '',
  }
}

function getResponseText(responses, qid) {
  const payload = responses?.[qid]
  if (!payload) return ''
  if (typeof payload === 'string') return payload
  return payload.text || payload.raw_transcript || ''
}

function normalizePatientQuestionnaire(responses = {}) {
  const labels = {
    Q1: 'Q1 주호소',
    Q2: 'Q2 시작 시점',
    Q3: 'Q3 복약·경과',
    Q4: 'Q4 환자 질문',
  }

  return ['Q1', 'Q2', 'Q3', 'Q4']
    .map(qid => {
      const payload = responses?.[qid]
      const original = getResponseText(responses, qid)
      const standardized = getStandardizedText(payload)
      if (!original && !standardized) return null
      return {
        id: qid,
        label: labels[qid] || qid,
        original,
        standardized,
      }
    })
    .filter(Boolean)
}

function getStandardizedText(payload) {
  if (!payload || typeof payload === 'string') return ''
  return (
    payload.structured?.standardized_text ||
    payload.dialect_normalization?.standardized_text ||
    payload.standardized_text ||
    payload.standard ||
    payload.normalized_text ||
    ''
  )
}

function normalizeVisitType(value) {
  if (value === '재진' || value === 'followup') return 'followup'
  return 'initial'
}

function categoryToKorean(cat) {
  const m = {
    drug_drug_interaction: '복약 상호작용',
    supplement_drug_interaction: '영양제 병용',
    food_drug_interaction: '음식-약 상호작용',
    treatment_duration: '복약 기간',
    followup_visit: '재내원 기준',
    prognosis: '예후·회복',
    general_health_info: '건강정보',
    prognosis_concern: '심각성 우려',
    '복약질문': '복약 질문',
    '건강식품질문': '건강식품 질문',
    '검사질문': '검사 질문',
    '재방문질문': '재방문 질문',
    '생활관리질문': '생활관리 질문',
    '기타질문': '기타 질문',
    other: '기타',
  }
  return m[cat] || '환자 질문'
}
