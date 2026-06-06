import { sleep } from './client.js'

// 백엔드 없이 UI를 시연할 때 쓰는 가짜 STT 결과입니다.
// 운영 배포에서는 VITE_API_BASE_URL이 설정되므로 이 파일은 호출되지 않습니다.
export async function getMockTranscript(jobName) {
  await sleep(1200)

  if (jobName.startsWith('mock-flag-trigger-')) {
    const qId = jobName.replace('mock-flag-trigger-', '')
    const flagTexts = {
      Q1: '기침이 너무 심하고 가래에 피가 조금 묻어 나왔어요.',
      Q2: '어제부터 갑자기 심해졌고 피가 섞인 가래가 시작됐어요.',
      Q3: '기침이 더 심해졌고 오늘도 피가 조금 보였어요.',
      Q4: '혹시 결핵이나 폐암은 아닐까 걱정돼요.',
    }
    return { transcript: flagTexts[qId] || flagTexts.Q1, confidence: 0.91 }
  }

  const qId = jobName.split('-').pop()
  const mockTexts = {
    Q1_initial: '어제부터 목이 칼칼하고 코가 막혀요. 기침도 조금 나요.',
    Q2_initial: '어제 저녁부터 그랬어요. 추운 데 다녀온 뒤 시작된 것 같아요.',
    Q3_initial: '혈압약은 매일 아침 먹고 있고 영양제도 같이 먹어요.',
    Q4_initial: '혈압약이랑 감기약을 같이 먹어도 되는지 궁금해요. 양파즙도 같이 먹어도 되나요?',
    Q1_followup: '약 먹고 목은 조금 나아졌는데 코막힘은 그대로예요. 기침은 더 심해졌어요.',
    Q2_followup: '약은 먹었는데 몇 번 깜빡해서 못 먹은 날이 있었어요.',
    Q3_followup: '새로 생긴 증상은 없고 기침만 조금 심해진 것 같아요.',
    Q4_followup: '약을 언제까지 먹어야 하나요?',
  }
  return { transcript: mockTexts[qId] || mockTexts.Q1_initial, confidence: 0.93 }
}

// 목업 모드에서만 쓰는 가짜 extract/match/validate 결과입니다.
// 실제 성능 확인은 반드시 Bedrock/Transcribe가 연결된 백엔드로 진행해야 합니다.
export function mockProcessResponse(questionType, visitType, transcript) {
  if (questionType === 'chief_complaint') {
    return {
      spans: [
        { source_quote: '목이 칼칼하고', type: 'symptom', slot_ref: 'throat_irritation' },
        { source_quote: '코가 막혀요', type: 'symptom', slot_ref: 'nasal_obstruction' },
        { source_quote: '기침도 조금 나요', type: 'symptom', slot_ref: 'cough' },
      ],
      matched_slots: [
        { slot_id: 'throat_irritation', name: '목 불편감', score: 0.91, source_quote: '목이 칼칼하고' },
        { slot_id: 'nasal_obstruction', name: '코막힘', score: 0.88, source_quote: '코가 막혀요' },
        { slot_id: 'cough', name: '기침', score: 0.84, source_quote: '기침도 조금 나요' },
      ],
      validator_passed: true,
      safety_flag: null,
    }
  }

  if (questionType === 'progress') {
    return {
      spans: [
        { source_quote: '목은 조금 나아졌는데', type: 'progress_improved', slot_ref: 'throat_irritation' },
        { source_quote: '코막힘은 그대로예요', type: 'progress_unchanged', slot_ref: 'nasal_obstruction' },
        { source_quote: '기침은 더 심해졌어요', type: 'progress_worsened', slot_ref: 'cough' },
      ],
      matched_slots: [
        { slot_id: 'throat_irritation', name: '목 불편감', source_quote: '목은 조금 나아졌는데', span_type: 'progress_improved' },
        { slot_id: 'nasal_obstruction', name: '코막힘', source_quote: '코막힘은 그대로예요', span_type: 'progress_unchanged' },
        { slot_id: 'cough', name: '기침', source_quote: '기침은 더 심해졌어요', span_type: 'progress_worsened' },
      ],
      validator_passed: true,
      safety_flag: null,
    }
  }

  if (questionType === 'onset') {
    return {
      spans: [{ source_quote: '어제 저녁부터', type: 'onset' }],
      structured: {
        standardized_text: transcript,
        clinical_clues: [
          { category: '증상맥락', label: '시작시점', summary: '어제 저녁부터 증상 시작', source_quote: '어제 저녁부터', source_question: 'Q2', priority: '일반' },
        ],
      },
      validator_passed: true,
      safety_flag: null,
    }
  }

  if (questionType === 'adherence') {
    return {
      spans: [{ source_quote: '몇 번 깜빡해서', type: 'adherence_gap' }],
      structured: {
        standardized_text: transcript,
        clinical_clues: [
          { category: '복약순응도', label: '복약누락', summary: '복약을 몇 차례 누락함', source_quote: '몇 번 깜빡해서', source_question: 'Q2', priority: '일반' },
        ],
      },
      validator_passed: true,
      safety_flag: null,
    }
  }

  if (questionType === 'current_medications') {
    return {
      spans: [],
      structured: {
        standardized_text: transcript,
        clinical_clues: [
          { category: '복약정보', label: '복용중', summary: '혈압약과 영양제 복용 중', source_quote: transcript, source_question: 'Q3', priority: '일반' },
        ],
      },
      validator_passed: true,
      safety_flag: null,
    }
  }

  if (questionType === 'patient_questions' || questionType === 'unresolved_questions') {
    const questions = transcript.includes('양파즙')
      ? [
          { category: 'drug_drug_interaction', summary: '혈압약과 감기약 병용 가능 여부 문의', original_quote: '혈압약이랑 감기약을 같이 먹어도 되는지 궁금해요' },
          { category: 'food_drug_interaction', summary: '양파즙 병용 가능 여부 문의', original_quote: '양파즙도 같이 먹어도 되나요' },
        ]
      : [
          { category: 'treatment_duration', summary: '복약 기간 문의', original_quote: transcript },
        ]
    return {
      spans: [],
      structured: { standardized_text: transcript, questions },
      validator_passed: true,
      safety_flag: null,
    }
  }

  return { spans: [], structured: { standardized_text: transcript }, validator_passed: true, safety_flag: null }
}

// 목업 모드 안내문 생성 결과입니다.
export function mockPatientGuide(answers) {
  return {
    generated_at: new Date().toISOString(),
    items: answers.map((answer) => ({
      question: answer.question_summary,
      answer_simple: [
        '진료실에서 안내받은 내용대로 복용해 주세요.',
        '불편하거나 증상이 심해지면 병원에 다시 알려 주세요.',
      ],
      tts_emphasis_words: ['복용', '증상'],
    })),
    delivery_options: ['screen', 'tts', 'print'],
  }
}
