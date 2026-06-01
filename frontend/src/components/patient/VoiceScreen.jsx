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
    const timer = setTimeout(() => start(), 400)
    return () => clearTimeout(timer)
    // 질문이 바뀌면 새 STT 세션을 준비합니다. 자동 시작이 막히면 마이크 버튼으로 다시 시작할 수 있습니다.
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
    ? '마이크 버튼을 다시 눌러 말씀해 주세요.'
    : isRecording
      ? (transcript || '듣고 있어요. 한 문장으로 말씀해 주세요.')
      : (transcript || partialText || '말씀하실 준비가 되면 마이크를 눌러 주세요.')

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

        <div className="transcript-box transcript-box-v4 voice-live-box">
          <div className="transcript-text transcript-text-large voice-live-line">
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
        <button className="btn-primary" onClick={isRecording ? handleEnd : start} disabled={isProcessing}>
          {isProcessing ? '분석 중...' : isRecording ? '발화 마치기' : '녹음 시작'}
        </button>
      </div>
    </>
  )
}
