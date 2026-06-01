// Mock — 초진
// 원페이퍼 컴포넌트를 백엔드 없이 시연할 때 쓰는 정적 예시 데이터입니다.
// 실제 배포 모드에서는 getOnePager API 응답이 우선됩니다.
export const MOCK_INITIAL = {
  patient: {
    name: '김*자', age: 74, gender: '여성', department: '이비인후과',
    visit_type: 'initial', receivedAt: '10:30', audioDuration: 58
  },
  agenda: [
    { type: 'drug_drug_interaction', type_label: '복약 상호작용',
      summary: '혈압약-감기약 병용 가능 여부 문의',
      original_quote: '혈압약이랑 감기약을 같이 먹어도 되는지 궁금해요' },
    { type: 'food_drug_interaction', type_label: '음식-약 상호작용',
      summary: '양파즙 병용 가능 여부 문의',
      original_quote: '양파즙도 같이 먹어도 되나요' }
  ],
  full_q4_transcript: '혈압약이랑 감기약을 같이 먹어도 되는지 궁금해요. 양파즙도 같이 먹어도 되나요?',
  symptomSlots: [
    { name: '목 불편감', sub: '인후 자극', sourceQuote: '목이 칼칼하고', score: 0.91 },
    { name: '코막힘', sub: '비폐색', sourceQuote: '코가 맥혀요 (사투리 자동 매칭)', score: 0.88 },
    { name: '기침', sub: 'cough', sourceQuote: '기침도 조금 나요', score: 0.84 }
  ],
  clinicalClues: [
    {
      id: 'mock-c1', category: '증상맥락', label: '시작시점', summary: '어제부터',
      source_question: 'Q1', source_quote: '어제부터', priority: '일반',
      related_symptoms: ['목 불편감', '코막힘', '기침']
    },
    {
      id: 'mock-c2', category: '복약정보', label: '복용중', summary: '혈압약 복용 중',
      source_question: 'Q3', source_quote: '혈압약 먹고 있어요', priority: '일반',
      related_symptoms: []
    },
    {
      id: 'mock-c3', category: '증상맥락', label: '동반', summary: '기침도 동반',
      source_question: 'Q1', source_quote: '기침도 조금 나요', priority: '일반',
      related_symptoms: ['기침']
    }
  ],
  reviewItems: [
    '발열 여부와 실제 체온 확인',
    '가래 동반 여부와 색깔',
    '혈압약 ↔ 일반 감기약 병용 가능 여부 안내',
    '양파즙 병용 가능 여부 답변',
    '흡연력 및 알레르기 이력 (음성에서 미수집)'
  ],
  transferText: '74세 여성 환자. 어제부터 목 불편감과 코막힘 호소. 발열은 없다고 말함. 혈압약 복용 중 감기약 병용 가능 여부 문의.',
  safety_flag: null
}

// Mock — 재진 (위험 분기 시연용)
// v4: 변화 추적 카드 대신 "오늘 말한 불편함"으로 통일 (EMR 미연동)
export const MOCK_FOLLOWUP = {
  patient: {
    name: '김*자', age: 74, gender: '여성', department: '이비인후과',
    visit_type: 'followup', receivedAt: '11:15', audioDuration: 42
  },
  agenda: [
    { type: 'treatment_duration', type_label: '복약 기간',
      summary: '복약 기간 문의',
      original_quote: '이 약을 언제까지 먹어야 되나요' }
  ],
  full_q4_transcript: '이 약을 언제까지 먹어야 되나요?',
  uncategorized_remnant: '',
  symptomSlots: [
    { name: '기침', sub: 'cough · 악화', sourceQuote: '기침이 더 심해졌고', score: 0.89 },
    { name: '객혈', sub: 'hemoptysis · 신규 ⚠', sourceQuote: '어제는 피가 살짝 묻어 나왔어요', score: 0.93, alert: true },
  ],
  clinicalClues: [
    {
      id: 'mock-f1', category: '재진경과', label: '악화', summary: '기침이 더 심해짐',
      source_question: 'Q1', source_quote: '기침이 더 심해졌고', priority: '일반',
      related_symptoms: ['기침']
    },
    {
      id: 'mock-f2', category: '재진경과', label: '새 증상', summary: '객혈 새로 발생',
      source_question: 'Q1', source_quote: '피가 살짝 묻어 나왔어요', priority: '우선',
      related_symptoms: ['객혈']
    }
  ],
  reviewItems: [
    '[우선] 객혈 평가 (X-ray·객담 검사 고려)',
    '[우선] 객혈량과 시작 시점 확인',
    '기침 악화 패턴 평가',
    '복약 순응도 (저녁 누락) 영향 평가',
    '흡연력 재확인'
  ],
  transferText: '재진 환자. 환자 호소: 기침 악화 + 객혈 신규 발생 ("피가 살짝 묻어 나왔다"). 환자 미해결 질문: 복약 기간 문의.',
  safety_flag: {
    category: 'hemoptysis', label: '객혈 의증',
    severity: 'high', matched_pattern: '피가 살짝'
  }
}
