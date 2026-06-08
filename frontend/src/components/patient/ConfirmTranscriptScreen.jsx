import ScreenHeader from '../tablet/ScreenHeader.jsx'

export default function ConfirmTranscriptScreen({
  patient,
  visitType,
  question,
  stepIndex,
  transcript,
  isProcessing = false,
  onConfirm,
  onRetry,
  onStaffCall,
}) {
  return (
    <>
      <ScreenHeader
        patientName={`${patient.name} ${patient.honorific}`}
        subtitle={`${visitType === 'initial' ? '초진' : '재진'} · ${question.id}번 확인`}
        visitType={visitType}
        currentStep={stepIndex}
      />

      <div className="screen-body verify-body verify-body-v4">
        <h2 className="verify-title-large">제가 이렇게 들었어요</h2>
        <p className="verify-help-large">
          맞으면 다음으로 넘어가고, 다르면 다시 말씀해 주세요.
        </p>

        <div className="transcript-box transcript-box-v4">
          <div className="transcript-text transcript-text-large">
            “{transcript || '인식된 내용이 없습니다'}”
          </div>
        </div>
      </div>

      <div className="screen-footer">
        <button className="btn-help staff-button-wide" onClick={onStaffCall} disabled={isProcessing}>
          직원 도움
        </button>
        <button className="retry-v4 verify-footer-btn" onClick={onRetry} disabled={isProcessing}>
          다시 말할게요
        </button>
        <button className="confirm-v4 verify-footer-btn" onClick={onConfirm} disabled={isProcessing || !transcript}>
          {isProcessing ? '분석 중...' : '맞아요 · 다음'}
        </button>
      </div>
    </>
  )
}
