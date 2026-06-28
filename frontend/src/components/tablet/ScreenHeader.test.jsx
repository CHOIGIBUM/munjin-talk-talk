import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ScreenHeader from './ScreenHeader.jsx'

describe('ScreenHeader', () => {
  it('환자 이름과 부제를 렌더링', () => {
    render(<ScreenHeader patientName="홍*동 어르신" subtitle="초진 문진" visitType="initial" />)
    expect(screen.getByText('홍*동 어르신')).toBeInTheDocument()
    expect(screen.getByText('초진 문진')).toBeInTheDocument()
  })

  it('초진 visit 태그 표시', () => {
    render(<ScreenHeader patientName="X" subtitle="Y" visitType="initial" />)
    expect(screen.getByText('초진')).toBeInTheDocument()
  })

  it('재진 visit 태그 표시', () => {
    render(<ScreenHeader patientName="X" subtitle="Y" visitType="followup" />)
    expect(screen.getByText('재진')).toBeInTheDocument()
  })

  it('showVisitTag=false면 태그 숨김', () => {
    render(<ScreenHeader patientName="X" subtitle="Y" visitType="initial" showVisitTag={false} />)
    expect(screen.queryByText('초진')).not.toBeInTheDocument()
  })

  it('진행 바 세그먼트를 totalSteps만큼 렌더', () => {
    const { container } = render(<ScreenHeader patientName="X" subtitle="Y" currentStep={2} totalSteps={6} />)
    const segs = container.querySelectorAll('.seg')
    expect(segs).toHaveLength(6)
    // 0,1번은 done, 2번은 active
    expect(segs[0].className).toContain('done')
    expect(segs[2].className).toContain('active')
  })
})
