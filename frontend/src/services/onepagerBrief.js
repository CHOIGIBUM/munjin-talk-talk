// doctor_brief가 없거나 불완전할 때 화면이 비지 않도록 보조 요약을 만듭니다.
// 실제 의사용 task 생성은 백엔드 Nova Pro가 담당하고, 이 파일은 UI fallback만 담당합니다.

export function buildFallbackBrief({ visitType, symptomSlots, clinicalClues, agenda, safetyFlag }) {
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

export function buildHeadline({ visitType, symptomSlots, clinicalClues, agenda, safetyFlag }) {
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

function unique(values) {
  return Array.from(new Set(values.filter(Boolean)))
}
