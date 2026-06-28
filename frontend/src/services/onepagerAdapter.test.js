import { describe, it, expect } from 'vitest'
import { normalizeOnePager, normalizeAgendaSource } from './onepagerAdapter.js'

describe('normalizeOnePager', () => {
  it('null 입력에 null을 반환한다', () => {
    expect(normalizeOnePager(null)).toBeNull()
    expect(normalizeOnePager(undefined)).toBeNull()
  })

  it('onepager가 없는 raw에 null을 반환한다', () => {
    expect(normalizeOnePager({})).toBeNull()
    expect(normalizeOnePager({ session: {} })).toBeNull()
  })

  it('정상 onepager를 올바른 구조로 변환한다', () => {
    const raw = {
      session: {
        status: 'waiting_doctor',
        visit_type: 'initial',
        responses: {},
      },
      onepager: {
        patient_summary: {
          display_name: '홍*동',
          age_text: '75세',
          sex: '남',
          department: '이비인후과',
          received_at: '14:30',
        },
        symptom_slots: [
          {
            name: '기침',
            status: '있음',
            source_quote: '기침이 나요',
            alert: false,
          },
        ],
        agenda: [
          {
            type: 'treatment_duration',
            summary: '약은 언제까지 먹어야 하나요?',
            original_quote: '약 언제까지요?',
          },
        ],
        safety_flags: [],
        clinical_clues: [],
        review_items: [],
        unresolved_items: [],
      },
    }

    const result = normalizeOnePager(raw)
    expect(result).not.toBeNull()
    expect(result.patient.name).toBe('홍*동')
    expect(result.patient.age).toBe(75)
    expect(result.patient.gender).toBe('남')
    expect(result.symptomSlots).toHaveLength(1)
    expect(result.symptomSlots[0].name).toBe('기침')
    expect(result.agenda).toHaveLength(1)
    expect(result.agenda[0].summary).toContain('약')
  })

  it('visit_type이 재진이면 followup으로 정규화된다', () => {
    const raw = {
      session: { status: 'completed', visit_type: '재진' },
      onepager: {
        patient_summary: {},
        symptom_slots: [],
        agenda: [],
        safety_flags: [],
        clinical_clues: [],
        review_items: [],
        unresolved_items: [],
      },
    }
    const result = normalizeOnePager(raw)
    expect(result.patient.visit_type).toBe('followup')
  })

  it('safety_flag를 올바르게 정규화한다', () => {
    const raw = {
      session: { status: 'needs_priority' },
      onepager: {
        patient_summary: {},
        symptom_slots: [],
        agenda: [],
        safety_flags: [
          {
            category: 'hemoptysis',
            label: '객혈 의심',
            severity: 'high',
            matched_pattern: '피가 섞여',
            message: '위험 표현 감지',
          },
        ],
        clinical_clues: [],
        review_items: [],
        unresolved_items: [],
      },
    }
    const result = normalizeOnePager(raw)
    expect(result.safety_flag).not.toBeNull()
    expect(result.safety_flag.category).toBe('hemoptysis')
    expect(result.safety_flag.severity).toBe('high')
  })
})

describe('normalizeAgendaSource', () => {
  it('null 입력에서 빈 agenda를 반환한다', () => {
    const result = normalizeAgendaSource(null)
    expect(result.agenda).toEqual([])
    expect(result.full_q4_transcript).toBe('')
  })

  it('onepager에서 agenda를 정상 추출한다', () => {
    const raw = {
      session: { status: 'waiting_doctor', responses: { Q4: '약 언제까지 먹나요?' } },
      onepager: {
        patient_summary: {},
        symptom_slots: [],
        agenda: [{ type: 'treatment_duration', summary: '복약 기간 문의' }],
        safety_flags: [],
        clinical_clues: [],
        review_items: [],
        unresolved_items: [],
      },
    }
    const result = normalizeAgendaSource(raw)
    expect(result.agenda).toHaveLength(1)
    expect(result.full_q4_transcript).toBe('약 언제까지 먹나요?')
  })
})
