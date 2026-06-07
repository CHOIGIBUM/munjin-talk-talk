import ScreenHeader from '../tablet/ScreenHeader.jsx'

const ManualIntakeIcon = () => (
  <svg viewBox="0 0 64 64" fill="none" aria-hidden="true">
    <circle cx="32" cy="32" r="30" fill="#14A3A8" />
    <path
      d="M21 18h22a4 4 0 0 1 4 4v24a4 4 0 0 1-4 4H21a4 4 0 0 1-4-4V22a4 4 0 0 1 4-4z"
      fill="white"
      opacity="0.96"
    />
    <path d="M25 28h14M25 36h14M25 44h9" stroke="#0B2545" strokeWidth="3" strokeLinecap="round" />
    <path d="M43 16v8M21 16v8" stroke="white" strokeWidth="4" strokeLinecap="round" />
  </svg>
)

// 개인정보 동의를 거부한 경우 음성 문진을 시작하지 않고 수기 문진 전환을 안내합니다.
// 이 화면은 환자에게 불안감을 주지 않도록 "직원이 도와준다"는 다음 행동만 크게 보여줍니다.
export default function ManualIntakeScreen({ patient, visitType }) {
  return (
    <>
      <ScreenHeader
        patientName={`${patient.name} ${patient.honorific}`}
        subtitle="수기 문진 안내"
        visitType={visitType}
        showVisitTag={false}
      />

      <main className="screen-main manual-intake-main">
        <div className="manual-intake-icon">
          <ManualIntakeIcon />
        </div>

        <h2 className="manual-intake-title">수기 문진으로 도와드릴게요</h2>
        <p className="manual-intake-message">
          이 태블릿 문진은 종료되었습니다.<br />
          접수 직원이 직접 확인하고 입력해 드릴 예정입니다.
        </p>

        <div className="manual-intake-status">
          <span className="manual-intake-dot" />
          <span>직원 확인 대기 중</span>
        </div>
      </main>
    </>
  )
}
