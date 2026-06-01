const DEFAULT_PATIENT = {
  name: '환자',
  age: 0,
  gender: '-',
  department: '이비인후과',
  visit_type: 'initial',
  receivedAt: '--:--',
  audioDuration: 0,
}

export function normalizeOnePager(raw, fallback = null) {
  if (!raw) return fallback

  const current = normalizeCurrentBackend(raw)
  if (current) return current

  const legacy = normalizeLegacyBackend(raw)
  if (legacy) return legacy

  return fallback || raw
}

export function normalizeAgendaSource(raw, fallbackAgenda = []) {
  const normalized = normalizeOnePager(raw, null)
  return {
    agenda: normalized ? (normalized.agenda || []) : fallbackAgenda,
    full_q4_transcript: normalized?.full_q4_transcript || '',
    uncategorized_remnant: normalized?.uncategorized_remnant || '',
  }
}

function normalizeCurrentBackend(raw) {
  const session = raw.session || raw
  const onepager = session.onepager || raw.onepager
  if (!onepager) return null

  const visitType = normalizeVisitType(session.visit_type || raw.visit_type || onepager.patient_summary?.visit_type)
  const patient = normalizePatientSummary(onepager.patient_summary, visitType)
  const agenda = normalizeAgenda(onepager.agenda || [])
  const symptomSlots = normalizeSymptomSlots(onepager.symptom_slots || [])
  const safetyFlags = onepager.safety_flags || []
  const safetyFlag = normalizeSafetyFlag(safetyFlags[0])
  const clinicalClues = onepager.clinical_clues || []
  const doctorBrief = normalizeDoctorBrief(onepager.doctor_brief, {
    visitType,
    symptomSlots,
    clinicalClues,
    agenda,
    safetyFlag,
  })

  return {
    patient,
    agenda,
    full_q4_transcript: getResponseText(session.responses, 'Q4'),
    uncategorized_remnant: (onepager.unresolved_items || []).map(x => x.display_text || x.normalized_text || x.source_quote).filter(Boolean).join(' / '),
    symptomSlots,
    clinicalClues,
    doctorBrief,
    reviewItems: normalizeReviewItems(onepager.review_items || []),
    transferText: onepager.transfer_text || '',
    safety_flag: safetyFlag,
    safety_flags: safetyFlags,
    unresolvedItems: onepager.unresolved_items || [],
  }
}

function normalizeLegacyBackend(raw) {
  if (!raw.patient && !raw.symptom_card && !raw.transfer_text && !raw.symptomSlots) return null

  const visitType = normalizeVisitType(raw.visit_type || raw.patient?.visit_type)
  const patient = {
    name: raw.patient?.name_masked || raw.patient?.name || DEFAULT_PATIENT.name,
    age: raw.patient?.age || DEFAULT_PATIENT.age,
    gender: raw.patient?.gender || DEFAULT_PATIENT.gender,
    department: raw.patient?.department || DEFAULT_PATIENT.department,
    visit_type: visitType,
    receivedAt: raw.patient?.received_at || raw.patient?.receivedAt || DEFAULT_PATIENT.receivedAt,
    audioDuration: raw.patient?.audio_duration || raw.patient?.audioDuration || DEFAULT_PATIENT.audioDuration,
  }

  const agenda = normalizeAgenda(raw.agenda || [])
  const symptomSlots = raw.symptomSlots || normalizeLegacySymptomCard(raw.symptom_card)
  const safetyFlag = raw.safety_flag || null
  const clinicalClues = raw.clinical_clues || raw.clinicalClues || []
  const doctorBrief = normalizeDoctorBrief(raw.doctor_brief, {
    visitType,
    symptomSlots,
    clinicalClues,
    agenda,
    safetyFlag,
  })

  return {
    patient,
    agenda,
    full_q4_transcript: raw.full_q4_transcript || '',
    uncategorized_remnant: raw.uncategorized_remnant || '',
    symptomSlots,
    clinicalClues,
    doctorBrief,
    reviewItems: normalizeReviewItems(raw.review_items || raw.reviewItems || []),
    transferText: raw.transfer_text || raw.transferText || '',
    safety_flag: safetyFlag,
    safety_flags: safetyFlag ? [safetyFlag] : [],
    unresolvedItems: raw.unresolved_items || [],
  }
}

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

function normalizeSymptomSlots(slots) {
  return (slots || []).map(slot => ({
    name: slot.name || slot.display_text || '-',
    sub: slot.sub || slot.status || slot.source_question || '',
    sourceQuote: slot.sourceQuote || slot.source_quote || '',
    sourceQuestion: slot.sourceQuestion || slot.source_question || '',
    normalizedText: slot.normalized_text || '',
    status: slot.status || '',
    explain: slot.explain || '',
    score: Number(slot.score ?? 0),
    alert: Boolean(slot.alert),
  }))
}

function normalizeLegacySymptomCard(card) {
  if (!card) return []
  if (card.type === 'symptom_list') {
    return (card.slots || []).map(slot => ({
      name: slot.name,
      sub: slot.slot_id,
      sourceQuote: slot.source_quote,
      score: Number(slot.score ?? 0),
      alert: Boolean(slot.alert),
    }))
  }
  if (card.type === 'progress_tracking') {
    return (card.spans || []).map(span => ({
      name: slotIdToKorean(span.slot_ref),
      sub: span.slot_ref,
      sourceQuote: span.source_quote,
      score: Number(span.score ?? 1),
      alert: span.type === 'new_symptom' || span.slot_ref === 'hemoptysis',
    }))
  }
  return []
}

function normalizeReviewItems(items) {
  return (items || []).map(item => {
    if (typeof item === 'string') return item
    const text = item.text || item.summary || ''
    if (item.priority === '우선' && text && !text.startsWith('[우선]')) return `[우선] ${text}`
    return text
  }).filter(Boolean)
}

function normalizeDoctorBrief(brief, context) {
  if (brief?.sections?.length || brief?.headline) {
    return {
      headline: brief.headline || buildHeadline(context),
      priority: brief.priority || (context.safetyFlag ? '우선' : '일반'),
      sections: (brief.sections || []).map(normalizeBriefSection).filter(Boolean),
    }
  }

  return buildFallbackBrief(context)
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

function buildFallbackBrief({ visitType, symptomSlots, clinicalClues, agenda, safetyFlag }) {
  const priority = safetyFlag || clinicalClues?.some(c => c.priority === '우선') ? '우선' : '일반'
  const sections = []
  const symptoms = unique(symptomSlots?.map(s => s.name).filter(Boolean) || [])
  const course = clinicalClues?.filter(c => ['재진경과', '증상맥락'].includes(c.category)) || []
  const meds = clinicalClues?.filter(c => ['복약정보', '복약순응도', '약물반응'].includes(c.category)) || []

  if (safetyFlag) {
    sections.push({
      key: 'priority',
      title: '우선 확인',
      priority: '우선',
      summary: safetyFlag.message || `${safetyFlag.label || safetyFlag.category} 확인 필요`,
      items: [{ text: safetyFlag.message || safetyFlag.matched_pattern || '', source_question: '', source_quote: safetyFlag.matched_pattern || '' }],
    })
  }
  if (symptoms.length || course.length) {
    sections.push({
      key: 'symptom_course',
      title: '증상 및 경과',
      priority: course.some(c => c.priority === '우선') ? '우선' : '일반',
      summary: [
        symptoms.length ? `주호소 ${symptoms.join(', ')}` : '',
        summarizeClues(course),
      ].filter(Boolean).join(' / '),
      items: course.map(clueToBriefItem),
    })
  }
  if (meds.length) {
    sections.push({
      key: 'medication',
      title: '복약 및 반응',
      priority: meds.some(c => c.priority === '우선') ? '우선' : '일반',
      summary: summarizeClues(meds),
      items: meds.map(clueToBriefItem),
    })
  }
  if (agenda?.length) {
    sections.push({
      key: 'agenda',
      title: '환자 질문',
      priority: '일반',
      summary: unique(agenda.map(a => a.summary).filter(Boolean)).join(', '),
      items: agenda.map(a => ({ text: a.summary, source_question: a.source_question || 'Q4', source_quote: a.original_quote || '' })),
    })
  }

  return {
    headline: buildHeadline({ visitType, symptomSlots, clinicalClues, agenda, safetyFlag }),
    priority,
    sections,
  }
}

function buildHeadline({ visitType, symptomSlots, clinicalClues, agenda, safetyFlag }) {
  const parts = []
  const symptoms = unique(symptomSlots?.map(s => s.name).filter(Boolean) || [])
  if (safetyFlag) parts.push(`우선 확인: ${safetyFlag.label || safetyFlag.category}`)
  if (symptoms.length) parts.push(`증상: ${symptoms.slice(0, 4).join(', ')}`)
  const course = clinicalClues?.find(c => c.category === '재진경과') || clinicalClues?.find(c => c.category === '증상맥락')
  if (course) parts.push(`${visitType === 'followup' ? '경과' : '맥락'}: ${course.summary || course.source_quote}`)
  const med = clinicalClues?.find(c => ['복약정보', '복약순응도', '약물반응'].includes(c.category))
  if (med) parts.push(`복약: ${med.summary || med.source_quote}`)
  if (agenda?.length) parts.push(`질문: ${agenda[0].summary}`)
  return parts.join(' | ') || '문진 요약'
}

function summarizeClues(clues, limit = 4) {
  return unique((clues || []).slice(0, limit).map(c => {
    if (c.label && c.summary && !c.summary.includes(c.label)) return `${c.label}: ${c.summary}`
    return c.summary || c.source_quote
  }).filter(Boolean)).join(', ')
}

function clueToBriefItem(clue) {
  return {
    text: clue.summary || clue.source_quote || '',
    source_question: clue.source_question || '',
    source_quote: clue.source_quote || '',
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

function normalizeVisitType(value) {
  if (value === '재진' || value === 'followup') return 'followup'
  return 'initial'
}

function unique(values) {
  return Array.from(new Set(values.filter(Boolean)))
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

function slotIdToKorean(id) {
  const m = {
    cough: '기침',
    throat_irritation: '목 불편감',
    nasal_obstruction: '코막힘',
    rhinorrhea: '콧물',
    fever: '열',
    sputum: '가래',
    dyspnea: '호흡곤란',
    hemoptysis: '객혈',
    chest_pain: '흉통',
    wheezing: '천명음',
    headache: '두통',
    sneezing: '재채기',
    voice_change: '음성 변화',
    sore_throat: '인후통',
  }
  return m[id] || id || '-'
}
