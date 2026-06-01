import { useEffect } from 'react'
import ScreenHeader from '../tablet/ScreenHeader.jsx'
import { useStreamingTranscribe } from '../../hooks/useStreamingTranscribe.js'

const MicIcon = () => (
  <svg viewBox="0 0 24 24" fill="none">
    <rect x="9" y="3" width="6" height="14" rx="3" fill="currentColor" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v4M9 22h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
)

function formatTime(seconds) {
  const m = String(Math.floor(seconds / 60)).padStart(2, '0')
  const s = String(seconds % 60).padStart(2, '0')
  return `${m}:${s}`
}

// Q1~Q4 공통 음성 입력 화면입니다.
// 브라우저 마이크 음성을 Amazon Transcribe Streaming으로 보내고, 받은 텍스트만 다음 단계로 전달합니다.
export default function VoiceScreen({
  sessionId,
  patient,
  visitType,
  question,
  stepIndex,
  partialText = '',
  isProcessing = false,
  onFinish,
  onStaffCall,
}) {
  const { isRecording, transcript, error, elapsed, start, stop } = useStreamingTranscribe({
    sessionId,
    questionId: question.id,
    visitType,
  })

  useEffect(() => {
    const t = setTimeout(() => start(), 300)
    return () => clearTimeout(t)
    // 질문이 바뀔 때마다 새 스트리밍 세션을 시작합니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question.id])

  const handleEnd = async () => {
    const finalText = await stop()
    onFinish(finalText)
  }

  const handleMicClick = () => {
    if (isRecording) handleEnd()
    else start()
  }

  const displayTranscript = error
    ? '실시간 음성 인식 연결 오류입니다. 다시 말씀해 주세요.'
    : transcript || partialText || '말씀하신 내용이 여기에 바로 표시됩니다.'

  return (
    <>
      <ScreenHeader
        patientName={`${patient.name} ${patient.honorific}`}
        subtitle={`${visitType === 'initial' ? '초진' : '재진'} · ${question.id}번 질문`}
        visitType={visitType}
        currentStep={stepIndex}
      />

      <div className="screen-body voice-body">
        <span className="voice-badge">{question.badge}</span>
        <h2 className="voice-question" style={{ whiteSpace: 'pre-line' }}>
          {question.title}
        </h2>
        <p className="voice-sub" style={{ whiteSpace: 'pre-line' }}>
          {question.sub}
        </p>
        <div className="voice-example">
          <b>예시</b>{question.example}
        </div>

        <div className="transcript-box transcript-box-v4">
          <div className="transcript-text transcript-text-large">
            {displayTranscript}
          </div>
        </div>

        <div className="voice-mic-wrap">
          <button
            className={`voice-mic ${isRecording ? 'recording' : ''}`}
            onClick={handleMicClick}
            disabled={isProcessing}
            aria-label={isRecording ? '녹음 중지' : '녹음 시작'}
          >
            <MicIcon />
          </button>
          {isRecording && (
            <div className="voice-wave">
              <i /><i /><i /><i /><i /><i /><i /><i /><i />
            </div>
          )}
          <div className="voice-timer">
            {isProcessing ? '분석 중' : formatTime(elapsed)} <span>{isProcessing ? '잠시만 기다려 주세요' : '/ 01:00'}</span>
          </div>
        </div>

        {isProcessing && (
          <div className="voice-processing">
            말씀하신 내용을 문진 결과로 정리하는 중입니다. 보통 5~15초 정도 걸립니다.
          </div>
        )}
      </div>

      <div className="screen-footer">
        <button className="btn-help staff-button-wide" onClick={onStaffCall} disabled={isProcessing}>직원 도움</button>
        <button className="btn-primary" onClick={handleEnd} disabled={isProcessing}>
          {isProcessing ? '분석 중...' : '발화 마치기'}
        </button>
      </div>
    </>
  )
}
