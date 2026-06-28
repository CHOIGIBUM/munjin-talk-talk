import { describe, it, expect } from 'vitest'
import {
  INITIAL_RECEPTION_FORM,
  SESSION_STATUS_LABEL,
  MANUAL_INPUT_STATUSES,
  formatBirthDate,
  getBirthDateError,
  formatPhone,
} from './receptionUtils.js'

describe('INITIAL_RECEPTION_FORM', () => {
  it('샘플 PII가 기본값에 없다 (실명/생년월일 비어있음)', () => {
    expect(INITIAL_RECEPTION_FORM.fullName).toBe('')
    expect(INITIAL_RECEPTION_FORM.birthDate).toBe('')
    expect(INITIAL_RECEPTION_FORM.phone).toBe('')
  })

  it('기본 진료과/방문유형이 설정됨', () => {
    expect(INITIAL_RECEPTION_FORM.visitType).toBe('initial')
    expect(INITIAL_RECEPTION_FORM.department).toBeTruthy()
  })
})

describe('formatBirthDate', () => {
  it('숫자를 YYYY-MM-DD로 포맷', () => {
    expect(formatBirthDate('19500917')).toBe('1950-09-17')
  })

  it('4자리 이하는 그대로', () => {
    expect(formatBirthDate('1950')).toBe('1950')
  })

  it('6자리는 YYYY-MM', () => {
    expect(formatBirthDate('195009')).toBe('1950-09')
  })

  it('숫자 외 문자는 제거', () => {
    expect(formatBirthDate('1950-09-17')).toBe('1950-09-17')
  })

  it('불가능한 월(13월)은 이전 값으로 되돌림', () => {
    const result = formatBirthDate('195013', '1950-0')
    expect(result).toBe('1950-0')
  })

  it('미래 연도는 거부', () => {
    const futureYear = new Date().getFullYear() + 5
    const result = formatBirthDate(`${futureYear}`, '195')
    expect(result).toBe('195')
  })
})

describe('getBirthDateError', () => {
  it('정상 생년월일은 에러 없음', () => {
    expect(getBirthDateError('1950-09-17')).toBe('')
  })

  it('빈 값은 입력 요청 메시지', () => {
    expect(getBirthDateError('')).toContain('입력')
  })

  it('8자리 미만은 형식 에러', () => {
    expect(getBirthDateError('1950-09')).toContain('8자리')
  })

  it('존재하지 않는 날짜(2월 30일) 거부', () => {
    expect(getBirthDateError('1950-02-30')).toContain('존재하지 않는')
  })

  it('1900년 이전 거부', () => {
    expect(getBirthDateError('1899-01-01')).toContain('연도')
  })

  it('미래 날짜 거부', () => {
    const next = new Date()
    next.setFullYear(next.getFullYear() + 1)
    const y = next.getFullYear()
    expect(getBirthDateError(`${y}-01-01`)).toContain('연도')
  })
})

describe('formatPhone', () => {
  it('11자리를 3-4-4로 포맷', () => {
    expect(formatPhone('01012345678')).toBe('010-1234-5678')
  })

  it('3자리 이하는 그대로', () => {
    expect(formatPhone('010')).toBe('010')
  })

  it('숫자 외 제거', () => {
    expect(formatPhone('010-1234-5678')).toBe('010-1234-5678')
  })

  it('11자리 초과는 잘림', () => {
    expect(formatPhone('010123456789999')).toBe('010-1234-5678')
  })
})

describe('SESSION_STATUS_LABEL & MANUAL_INPUT_STATUSES', () => {
  it('주요 상태 라벨이 한글로 정의됨', () => {
    expect(SESSION_STATUS_LABEL.waiting_tablet).toBeTruthy()
    expect(SESSION_STATUS_LABEL.waiting_doctor).toBeTruthy()
    expect(SESSION_STATUS_LABEL.reviewed).toBeTruthy()
  })

  it('수동 입력 가능 상태 집합에 staff_help 포함', () => {
    expect(MANUAL_INPUT_STATUSES.has('staff_help')).toBe(true)
    expect(MANUAL_INPUT_STATUSES.has('waiting_doctor')).toBe(false)
  })
})
