import { describe, it, expect } from 'vitest'
import { QUESTIONS, FLOW_STEPS, PROGRESS_SEGMENTS } from './questions.js'
import { questionTextForBackend } from './questionText.js'

describe('QUESTIONS 스키마', () => {
  it('초진/재진 각각 4문항', () => {
    expect(QUESTIONS.initial).toHaveLength(4)
    expect(QUESTIONS.followup).toHaveLength(4)
  })

  it('모든 문항에 id, question_type, title 존재', () => {
    for (const visit of ['initial', 'followup']) {
      for (const q of QUESTIONS[visit]) {
        expect(q.id).toBeTruthy()
        expect(q.question_type).toBeTruthy()
        expect(q.title).toBeTruthy()
      }
    }
  })

  it('초진 Q1은 chief_complaint (Hybrid IR 대상)', () => {
    const q1 = QUESTIONS.initial[0]
    expect(q1.id).toBe('Q1')
    expect(q1.question_type).toBe('chief_complaint')
    expect(q1.processing).toBe('llm_with_match')
  })

  it('재진 Q1은 progress, Q3은 new_symptoms (증상 문항)', () => {
    expect(QUESTIONS.followup[0].question_type).toBe('progress')
    expect(QUESTIONS.followup[2].question_type).toBe('new_symptoms')
  })

  it('증상 문항만 llm_with_match, 나머지는 llm_only', () => {
    const symptomTypes = new Set(['chief_complaint', 'progress', 'new_symptoms'])
    for (const visit of ['initial', 'followup']) {
      for (const q of QUESTIONS[visit]) {
        if (symptomTypes.has(q.question_type)) {
          expect(q.processing).toBe('llm_with_match')
        } else {
          expect(q.processing).toBe('llm_only')
        }
      }
    }
  })

  it('문항 id는 visit 내에서 유일', () => {
    for (const visit of ['initial', 'followup']) {
      const ids = QUESTIONS[visit].map(q => q.id)
      expect(new Set(ids).size).toBe(ids.length)
    }
  })
})

describe('FLOW_STEPS', () => {
  it('visit_type으로 시작하고 done으로 끝남', () => {
    expect(FLOW_STEPS[0]).toBe('visit_type')
    expect(FLOW_STEPS[FLOW_STEPS.length - 1]).toBe('done')
  })

  it('Q1~Q4 음성+검증 단계 포함', () => {
    expect(FLOW_STEPS).toContain('q1')
    expect(FLOW_STEPS).toContain('q1_verify')
    expect(FLOW_STEPS).toContain('q4_verify')
  })

  it('PROGRESS_SEGMENTS는 6', () => {
    expect(PROGRESS_SEGMENTS).toBe(6)
  })
})

describe('questionTextForBackend', () => {
  it('title을 정규화해 반환', () => {
    const q = { title: '어디가 불편하셔서\n오셨어요?' }
    const text = questionTextForBackend(q)
    expect(text).toBe('어디가 불편하셔서 오셨어요?')
    expect(text).not.toContain('\n')
  })

  it('prompt_text가 있으면 우선 사용', () => {
    const q = { title: '화면용', prompt_text: '백엔드용 질문' }
    expect(questionTextForBackend(q)).toBe('백엔드용 질문')
  })

  it('null/빈 입력은 빈 문자열', () => {
    expect(questionTextForBackend(null)).toBe('')
    expect(questionTextForBackend({})).toBe('')
  })
})
