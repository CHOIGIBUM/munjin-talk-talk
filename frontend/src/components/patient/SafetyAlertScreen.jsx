import ScreenHeader from '../tablet/ScreenHeader.jsx'

// 객혈 등 우선 확인이 필요한 표현이 감지되었을 때 보여주는 안심 안내 화면입니다.
// 환자를 놀라게 하지 않으면서 직원 확인 또는 문진 종료를 선택할 수 있게 합니다.
const AlertIcon = () => (
  <svg viewBox="0 0 64 64" fill="none">
    <circle cx="32" cy="32" r="30" fill="#DBEAFE"/>
    <path
      d="M32 14l16 7v10c0 11-7 18-16 21-9-3-16-10-16-21V21l16-7z"
      fill="#2563EB"
    />
    <path d="M24 32l6 6 11-13" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

export default function SafetyAlertScreen({
  patient,
  visitType,
  stepIndex,
  onContinue,
  onEnd,
  isEnding = false,
}) {
  return (
    <>
      <ScreenHeader
        patientName={`${patient.name} ${patient.honorific}`}
        subtitle="직원이 확인 중입니다"
        visitType={visitType}
        currentStep={stepIndex}
      />

      <div className="screen-body safety-body safety-body-v4">
        <div className="safety-icon-wrap">
          <AlertIcon />
        </div>

        <h2 className="safety-title safety-title-large">
          잠시 직원이 확인할게요
        </h2>

        <p className="safety-message safety-message-large">
          문진을 더 정확하게 진행하기 위해<br/>
          접수 직원에게 도움 요청을 보냈습니다.
        </p>

        <div className="safety-reassure safety-reassure-v4">
          놀라실 필요 없어요.<br/>
          화면이 멈춘 것이 아니라 직원 확인 후 계속 진행할 수 있습니다.
        </div>
      </div>

      <div className="screen-footer">
        <div className="safety-footer-actions">
          <button
            type="button"
            className="btn-help safety-end-button"
            onClick={onEnd}
            disabled={isEnding}
          >
            직원에게 맡기고 종료
          </button>
          <button
            type="button"
            className="btn-primary safety-continue-button"
            onClick={onContinue}
            disabled={isEnding}
          >
            직원과 계속하기
          </button>
        </div>
      </div>
    </>
  )
}
