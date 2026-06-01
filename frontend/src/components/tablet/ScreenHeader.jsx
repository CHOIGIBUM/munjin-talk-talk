// 모든 태블릿 화면 상단의 공통 헤더
// - 로고 + 환자 이름/부제
// - 우측 visit 태그 (선택)
// - 진행 바 (6세그먼트)

import logoUrl from '../../assets/munjin-logo.svg'

export default function ScreenHeader({
  patientName,
  subtitle,
  visitType,
  currentStep = 0,      // 0~5 (접수, Q1~Q4, 완료)
  totalSteps = 6,
  showVisitTag = true
}) {
  const segments = Array.from({ length: totalSteps }, (_, i) => {
    if (i < currentStep) return 'done'
    if (i === currentStep) return 'active'
    return ''
  })

  return (
    <div className="screen-header">
      <div className="screen-header-top">
        <div className="screen-header-left">
          <img className="screen-logo" src={logoUrl} alt="" aria-hidden="true" />
          <div>
            <div className="screen-title">{patientName}</div>
            <div className="screen-sub">{subtitle}</div>
          </div>
        </div>
        {showVisitTag && visitType && (
          <span className={`visit-tag ${visitType}`}>
            {visitType === 'initial' ? '초진' : '재진'}
          </span>
        )}
      </div>
      <div className="progress">
        {segments.map((state, i) => (
          <span key={i} className={`seg ${state}`} />
        ))}
      </div>
    </div>
  )
}
