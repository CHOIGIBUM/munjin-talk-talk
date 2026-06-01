import { useCallback, useState } from 'react'
import TabletFrame from '../tablet/TabletFrame.jsx'
import VisitTypeScreen from './VisitTypeScreen.jsx'
import VoiceScreen from './VoiceScreen.jsx'
import ConfirmTranscriptScreen from './ConfirmTranscriptScreen.jsx'
import SafetyAlertScreen from './SafetyAlertScreen.jsx'
import StaffCallScreen from './StaffCallScreen.jsx'
import DoneScreen from './DoneScreen.jsx'
import { QUESTIONS } from '../../config/questions.js'
import { detectSafetyKeyword } from '../../config/safetyKeywords.js'
import { processTranscript, createSession, isMockApiEnabled } from '../../services/api.js'

const MOCK_PATIENT = {
  name: '김*자',
  honorific: '어르신',
  age: 74,
  gender: '여성',
  receiptId: 'A-0427',
}

const EMPTY_PATIENT = {
  name: '환자',
  honorific: '',
  age: '-',
  gender: '-',
  receiptId: '-',
}

const STEPS = {
  VISIT_TYPE: 'visit_type',
  Q_VOICE: 'q_voice',
  Q_CONFIRM: 'q_confirm',
  SAFETY_ALERT: 'safety_alert',
  STAFF_CALL: 'staff_call',
  DONE: 'done',
}

// 환자 태블릿 문진의 상태 머신입니다.
// 실시간 Transcribe가 화면에 바로 텍스트를 보여주므로 별도 STT 확인 화면은 두지 않습니다.
export default function PatientFlow({
  initialVisitType = null,
  patient = null,
  sessionId = null,
  queueNumber = null,
  frameVariant = 'preview',
  skipVisitTypeWhenPreset = true,
  onTranscriptConfirmed,
  onComplete,
  onStaffCallRequest,
}) {
  const [step, setStep] = useState(initialVisitType && skipVisitTypeWhenPreset ? STEPS.Q_VOICE : STEPS.VISIT_TYPE)
  const [visitType, setVisitType] = useState(initialVisitType)
  const [questionIndex, setQuestionIndex] = useState(0)
  const [transcript, setTranscript] = useState('')
  const [safetyKeyword, setSafetyKeyword] = useState(null)
  const [answers, setAnswers] = useState([])
  const [session] = useState(() => sessionId ? { sessionId, startedAt: new Date().toISOString() } : createSession())
  const [prevStep, setPrevStep] = useState(null)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [pendingSafetyResult, setPendingSafetyResult] = useState(null)
  const [isEndingIntake, setIsEndingIntake] = useState(false)
  const [intakeStopped, setIntakeStopped] = useState(false)

  const questions = visitType ? QUESTIONS[visitType] : []
  const currentQuestion = questions[questionIndex]
  const displayPatient = patient || (isMockApiEnabled() ? MOCK_PATIENT : EMPTY_PATIENT)

  const handleStaffCall = useCallback(() => {
    onStaffCallRequest?.({
      sessionId: session.sessionId,
      questionId: currentQuestion?.id || null,
      step,
    })
    setPrevStep(step)
    setStep(STEPS.STAFF_CALL)
  }, [currentQuestion, onStaffCallRequest, session.sessionId, step])

  const handleStaffCallReturn = useCallback(() => {
    setStep(prevStep || STEPS.VISIT_TYPE)
    setPrevStep(null)
  }, [prevStep])

  const handleVisitTypeConfirm = useCallback((path) => {
    setVisitType(path)
    setQuestionIndex(0)
    setTranscript('')
    setStep(STEPS.Q_VOICE)
  }, [])

  const advanceWithConfirmedAnswer = useCallback((result, answerText) => {
    if (!currentQuestion) return
    const confirmedAnswer = {
      id: currentQuestion.id,
      questionId: currentQuestion.id,
      transcript: answerText,
      question_type: currentQuestion.question_type,
      result,
    }
    const nextAnswers = [...answers, confirmedAnswer]

    onTranscriptConfirmed?.(confirmedAnswer)
    setAnswers(nextAnswers)
    setTranscript('')
    setPendingSafetyResult(null)
    setSafetyKeyword(null)

    if (questionIndex >= questions.length - 1) {
      onComplete?.({
        sessionId: session.sessionId,
        visitType,
        answers: nextAnswers,
      })
      setStep(STEPS.DONE)
      return
    }

    setQuestionIndex(questionIndex + 1)
    setStep(STEPS.Q_VOICE)
  }, [
    answers,
    currentQuestion,
    onComplete,
    onTranscriptConfirmed,
    questionIndex,
    questions.length,
    session.sessionId,
    visitType,
  ])

  const runBackendPipeline = useCallback(async (answerText) => {
    if (!currentQuestion) throw new Error('missing_question')
    return processTranscript({
      sessionId: session.sessionId,
      questionId: currentQuestion.id,
      questionType: currentQuestion.question_type,
      visitType,
      transcript: answerText,
    })
  }, [currentQuestion, session.sessionId, visitType])

  const handleVoiceFinish = useCallback((sttText) => {
    const answerText = String(sttText || '').trim()
    if (!answerText) {
      setTranscript('음성 인식 결과가 비어 있습니다. 다시 말씀해 주세요.')
      return
    }
    setTranscript(answerText)
    setStep(STEPS.Q_CONFIRM)
  }, [])

  const handleRetryTranscript = useCallback(() => {
    setTranscript('')
    setStep(STEPS.Q_VOICE)
  }, [])

  const handleConfirmTranscript = useCallback(async () => {
    const answerText = String(transcript || '').trim()
    if (!answerText || answerText.includes('음성 인식 결과가 비어 있습니다')) {
      setStep(STEPS.Q_VOICE)
      return
    }
    setIsTranscribing(true)

    try {
      const safety = detectSafetyKeyword(answerText)
      if (safety && safety.severity === 'high') {
        setSafetyKeyword(safety)
        setPendingSafetyResult(null)
        onStaffCallRequest?.({
          sessionId: session.sessionId,
          questionId: currentQuestion?.id || null,
          step: STEPS.SAFETY_ALERT,
          reason: 'safety_keyword',
        })
        setStep(STEPS.SAFETY_ALERT)
        return
      }

      const result = await runBackendPipeline(answerText)
      if (result.safety_flag && result.safety_flag.severity === 'high') {
        setSafetyKeyword(result.safety_flag)
        setPendingSafetyResult(result)
        setStep(STEPS.SAFETY_ALERT)
        return
      }

      advanceWithConfirmedAnswer(result, answerText)
    } catch (err) {
      console.error('STT/process failed:', err)
      setTranscript('문진 처리 중 오류가 발생했습니다. 다시 말씀해 주세요.')
      setStep(STEPS.Q_VOICE)
    } finally {
      setIsTranscribing(false)
    }
  }, [advanceWithConfirmedAnswer, currentQuestion, onStaffCallRequest, runBackendPipeline, session.sessionId, transcript])

  const handleSafetyContinue = useCallback(async () => {
    const answerText = transcript.trim()
    setIsTranscribing(true)
    try {
      if (pendingSafetyResult) {
        advanceWithConfirmedAnswer(pendingSafetyResult, answerText)
        return
      }
      if (!answerText) {
        setStep(STEPS.Q_VOICE)
        return
      }
      const result = await runBackendPipeline(answerText)
      advanceWithConfirmedAnswer(result, answerText)
    } catch (err) {
      console.error('Safety continue failed:', err)
      setStep(STEPS.Q_VOICE)
    } finally {
      setIsTranscribing(false)
    }
  }, [advanceWithConfirmedAnswer, pendingSafetyResult, runBackendPipeline, transcript])

  const handleSafetyEnd = useCallback(async () => {
    setIsEndingIntake(true)
    const answerText = transcript.trim()
    let nextAnswers = answers

    try {
      let result = pendingSafetyResult
      if (!result && answerText && currentQuestion) {
        result = await runBackendPipeline(answerText)
      }
      if (result && currentQuestion && answerText) {
        const confirmedAnswer = {
          id: currentQuestion.id,
          questionId: currentQuestion.id,
          transcript: answerText,
          question_type: currentQuestion.question_type,
          result,
        }
        nextAnswers = [...answers, confirmedAnswer]
        onTranscriptConfirmed?.(confirmedAnswer)
        setAnswers(nextAnswers)
      }
    } catch (err) {
      console.error('Safety end failed:', err)
    } finally {
      onComplete?.({
        sessionId: session.sessionId,
        visitType,
        answers: nextAnswers,
        stopped: true,
      })
      setTranscript('')
      setPendingSafetyResult(null)
      setSafetyKeyword(null)
      setIntakeStopped(true)
      setIsEndingIntake(false)
      setStep(STEPS.DONE)
    }
  }, [
    answers,
    currentQuestion,
    onComplete,
    onTranscriptConfirmed,
    pendingSafetyResult,
    runBackendPipeline,
    session.sessionId,
    transcript,
    visitType,
  ])

  const renderScreen = () => {
    switch (step) {
      case STEPS.VISIT_TYPE:
        return (
          <VisitTypeScreen
            patient={displayPatient}
            defaultVisitType={visitType}
            onConfirm={handleVisitTypeConfirm}
            onStaffCall={handleStaffCall}
          />
        )

      case STEPS.Q_VOICE:
        return (
          <VoiceScreen
            sessionId={session.sessionId}
            patient={displayPatient}
            visitType={visitType}
            question={currentQuestion}
            stepIndex={questionIndex + 1}
            partialText={transcript}
            isProcessing={isTranscribing}
            onFinish={handleVoiceFinish}
            onStaffCall={handleStaffCall}
          />
        )

      case STEPS.Q_CONFIRM:
        return (
          <ConfirmTranscriptScreen
            patient={displayPatient}
            visitType={visitType}
            question={currentQuestion}
            stepIndex={questionIndex + 1}
            transcript={transcript}
            isProcessing={isTranscribing}
            onConfirm={handleConfirmTranscript}
            onRetry={handleRetryTranscript}
            onStaffCall={handleStaffCall}
          />
        )

      case STEPS.SAFETY_ALERT:
        return (
          <SafetyAlertScreen
            patient={displayPatient}
            visitType={visitType}
            stepIndex={questionIndex + 1}
            safetyKeyword={safetyKeyword}
            onContinue={handleSafetyContinue}
            onEnd={handleSafetyEnd}
            isEnding={isEndingIntake || isTranscribing}
          />
        )

      case STEPS.STAFF_CALL:
        return (
          <StaffCallScreen
            patient={displayPatient}
            onReturn={handleStaffCallReturn}
            returnLabel={prevStep === STEPS.VISIT_TYPE ? '진료 화면으로 돌아가기' : '문진 계속하기'}
          />
        )

      case STEPS.DONE:
        return (
          <DoneScreen
            patient={displayPatient}
            visitType={visitType}
            stopped={intakeStopped}
            queueNumber={queueNumber}
          />
        )

      default:
        return null
    }
  }

  return (
    <TabletFrame visitType={visitType} variant={frameVariant}>
      {renderScreen()}
    </TabletFrame>
  )
}
