import { describe, it, expect } from 'vitest'
import { detectSafetyKeyword, SAFETY_KEYWORDS } from './safetyKeywords.js'

describe('detectSafetyKeyword', () => {
  it('객혈 키워드를 감지한다', () => {
    const result = detectSafetyKeyword('가래에 피가 섞여 나왔어요')
    expect(result).not.toBeNull()
    expect(result.category).toBe('hemoptysis')
    expect(result.severity).toBe('high')
  })

  it('호흡곤란 키워드를 감지한다', () => {
    const result = detectSafetyKeyword('숨을 못 쉬겠어요')
    expect(result).not.toBeNull()
    expect(result.category).toBe('dyspnea')
  })

  it('흉통 키워드를 감지한다', () => {
    const result = detectSafetyKeyword('가슴이 너무 아파요')
    expect(result).not.toBeNull()
    expect(result.category).toBe('chest_pain')
  })

  it('의식 저하를 감지한다', () => {
    const result = detectSafetyKeyword('갑자기 기절했어요')
    expect(result).not.toBeNull()
    expect(result.category).toBe('consciousness')
  })

  it('토혈을 감지한다', () => {
    const result = detectSafetyKeyword('토혈 증상이 있어요')
    expect(result).not.toBeNull()
    expect(result.category).toBe('hematemesis')
  })

  it('일반 텍스트에서는 null을 반환한다', () => {
    expect(detectSafetyKeyword('목이 좀 칼칼해요')).toBeNull()
    expect(detectSafetyKeyword('기침이 나요')).toBeNull()
    expect(detectSafetyKeyword('콧물이 줄줄 흘러요')).toBeNull()
  })

  it('빈 문자열에서는 null을 반환한다', () => {
    expect(detectSafetyKeyword('')).toBeNull()
    expect(detectSafetyKeyword(null)).toBeNull()
    expect(detectSafetyKeyword(undefined)).toBeNull()
  })

  it('공백/특수문자 제거 후에도 감지한다', () => {
    // STT에서 띄어쓰기가 흔들리는 경우
    const result = detectSafetyKeyword('피섞인가래')
    expect(result).not.toBeNull()
    expect(result.category).toBe('hemoptysis')
  })

  it('감지 결과에 position을 포함한다', () => {
    const result = detectSafetyKeyword('어제부터 객혈이 있어요')
    expect(result).not.toBeNull()
    expect(typeof result.position).toBe('number')
    expect(result.position).toBeGreaterThanOrEqual(0)
  })
})

describe('SAFETY_KEYWORDS 구조', () => {
  it('최소 5개 카테고리가 정의되어 있다', () => {
    expect(SAFETY_KEYWORDS.length).toBeGreaterThanOrEqual(5)
  })

  it('각 항목에 필수 필드가 있다', () => {
    for (const item of SAFETY_KEYWORDS) {
      expect(item.label).toBeTruthy()
      expect(item.category).toBeTruthy()
      expect(item.severity).toBe('high')
      expect(item.terms.length).toBeGreaterThan(0)
    }
  })
})
