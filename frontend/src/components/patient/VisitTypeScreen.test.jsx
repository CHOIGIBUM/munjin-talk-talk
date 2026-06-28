import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import VisitTypeScreen from './VisitTypeScreen.jsx'

const patient = { name: '홍*동', age: 75, gender: '남성', receiptId: 'R-0001' }

describe('VisitTypeScreen', () => {
  it('환자 정보와 질문을 렌더링', () => {
    render(<VisitTypeScreen patient={patient} onConfirm={vi.fn()} onStaffCall={vi.fn()} />)
    expect(screen.getByText('홍*동')).toBeInTheDocument()
    expect(screen.getByText('오늘 진료가 처음이신가요?')).toBeInTheDocument()
    expect(screen.getByText('처음 왔어요')).toBeInTheDocument()
    expect(screen.getByText('전에 왔었어요')).toBeInTheDocument()
  })

  it('초기엔 시작 버튼이 비활성', () => {
    render(<VisitTypeScreen patient={patient} onConfirm={vi.fn()} onStaffCall={vi.fn()} />)
    const startBtn = screen.getByText(/먼저 위에서 한 가지 골라주세요/)
    expect(startBtn).toBeDisabled()
  })

  it('초진 선택 후 시작하면 onConfirm(initial) 호출', () => {
    const onConfirm = vi.fn()
    render(<VisitTypeScreen patient={patient} onConfirm={onConfirm} onStaffCall={vi.fn()} />)
    fireEvent.click(screen.getByText('처음 왔어요'))
    const startBtn = screen.getByText(/초진 문진 시작하기/)
    expect(startBtn).not.toBeDisabled()
    fireEvent.click(startBtn)
    expect(onConfirm).toHaveBeenCalledWith('initial')
  })

  it('재진 선택 시 재진 문진 시작 문구', () => {
    const onConfirm = vi.fn()
    render(<VisitTypeScreen patient={patient} onConfirm={onConfirm} onStaffCall={vi.fn()} />)
    fireEvent.click(screen.getByText('전에 왔었어요'))
    fireEvent.click(screen.getByText(/재진 문진 시작하기/))
    expect(onConfirm).toHaveBeenCalledWith('followup')
  })

  it('직원 도움 버튼이 onStaffCall 호출', () => {
    const onStaffCall = vi.fn()
    render(<VisitTypeScreen patient={patient} onConfirm={vi.fn()} onStaffCall={onStaffCall} />)
    fireEvent.click(screen.getByText('직원 도움'))
    expect(onStaffCall).toHaveBeenCalledOnce()
  })

  it('defaultVisitType이 있으면 미리 선택됨', () => {
    const onConfirm = vi.fn()
    render(<VisitTypeScreen patient={patient} defaultVisitType="followup" onConfirm={onConfirm} onStaffCall={vi.fn()} />)
    // 이미 선택됐으므로 바로 시작 가능
    fireEvent.click(screen.getByText(/재진 문진 시작하기/))
    expect(onConfirm).toHaveBeenCalledWith('followup')
  })
})
