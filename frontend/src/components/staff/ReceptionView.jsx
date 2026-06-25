import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  createIntakeSession,
  deleteIntakeSession,
  getDoctorQueue,
  getIntakeSession,
  processTranscript,
  updateIntakeSession,
} from '../../services/api.js'
import { QUESTIONS } from '../../config/questions.js'
import { questionTextForBackend } from '../../config/questionText.js'
import logoUrl from '../../assets/munjin-logo.svg'
import ReceptionForm from './ReceptionForm.jsx'
import ReceptionManualInput from './ReceptionManualInput.jsx'
import ReceptionSessionList from './ReceptionSessionList.jsx'
import { formatBirthDate, getBirthDateError, INITIAL_RECEPTION_FORM } from './receptionUtils.js'
import { sessionUrl } from '../../services/api/client.js'
import './ReceptionView.css'

// 접수처 화면의 controller 역할만 담당합니다.
// 실제 폼/목록/직원 대리 입력 UI는 하위 컴포넌트로 분리했습니다.
export default function ReceptionView() {
  const navigate = useNavigate()
  const [form, setForm] = useState(INITIAL_RECEPTION_FORM)
  const [sessions, setSessions] = useState([])
  const [created, setCreated] = useState(null)
  const [manualSession, setManualSession] = useState(null)
  const [manualTexts, setManualTexts] = useState({})
  const [manualOriginalTexts, setManualOriginalTexts] = useState({})
  const [manualVisitType, setManualVisitType] = useState('initial')
  const [manualOriginalVisitType, setManualOriginalVisitType] = useState('initial')
  const [manualStatus, setManualStatus] = useState('')
  const [manualSubmitting, setManualSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [isCreatingSession, setIsCreatingSession] = useState(false)

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await getDoctorQueue({ role: 'staff' }))
    } catch (error) {
      console.error('reception queue refresh failed:', error)
      setSessions([])
    }
  }, [])

  useEffect(() => {
    loadSessions()
    const timer = setInterval(loadSessions, 5000)
    return () => clearInterval(timer)
  }, [loadSessions])

  const waitingCount = useMemo(
    () => sessions.filter((session) => ['waiting_tablet', 'in_progress', 'staff_help'].includes(session.status)).length,
    [sessions]
  )

  const updateField = (key, value) => {
    setForm((prev) => {
      const nextValue = key === 'birthDate' ? formatBirthDate(value, prev.birthDate) : value
      return { ...prev, [key]: nextValue }
    })
    if (key === 'birthDate') setFormError('')
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (isCreatingSession) return
    const birthError = getBirthDateError(form.birthDate)
    if (birthError) {
      setFormError(birthError)
      return
    }
    setFormError('')
    setIsCreatingSession(true)
    try {
      const next = await createIntakeSession(form)
      await loadSessions()
      setCreated(next)
      setForm({ ...INITIAL_RECEPTION_FORM })
    } catch (error) {
      console.error('create session failed:', error)
      setFormError('문진 세션을 생성하지 못했습니다. 네트워크와 백엔드 상태를 확인해 주세요.')
    } finally {
      setIsCreatingSession(false)
    }
  }

  const handleDeleteSession = async (session) => {
    const patientName = session?.patient?.name || '해당 환자'
    if (!window.confirm(`${patientName} 문진 세션을 삭제할까요?`)) return

    try {
      await deleteIntakeSession(session.sessionId)
      if (created?.sessionId === session.sessionId) setCreated(null)
      if (manualSession?.sessionId === session.sessionId) closeManualInput()
      await loadSessions()
    } catch (error) {
      console.error('delete session failed:', error)
      setFormError('문진 세션을 삭제하지 못했습니다. 네트워크와 백엔드 상태를 확인해 주세요.')
    }
  }

  const openManualInput = async (session) => {
    setManualStatus('문진 내용을 불러오는 중입니다.')
    const detail = await getIntakeSession(session.sessionId, { role: 'staff' })
    const nextSession = detail || session
    const nextVisitType = nextSession.visitType || 'initial'
    const nextTexts = makeManualTextState(nextSession, nextVisitType)
    setManualSession(nextSession)
    setManualTexts(nextTexts)
    setManualOriginalTexts(nextTexts)
    setManualVisitType(nextVisitType)
    setManualOriginalVisitType(nextVisitType)
    setManualStatus('환자가 말한 내용을 직원이 대신 입력할 수 있습니다.')
  }

  const closeManualInput = () => {
    setManualSession(null)
    setManualTexts({})
    setManualOriginalTexts({})
    setManualVisitType('initial')
    setManualOriginalVisitType('initial')
    setManualStatus('')
    setManualSubmitting(false)
  }

  const updateManualText = (questionId, value) => {
    setManualTexts((prev) => ({ ...prev, [questionId]: value }))
  }

  const handleManualVisitTypeChange = (visitType) => {
    setManualVisitType(visitType)
    setManualStatus(
      visitType === manualOriginalVisitType
        ? '환자가 말한 내용을 직원이 대신 입력할 수 있습니다.'
        : '문진 유형이 변경되었습니다. 저장하면 세션에 반영됩니다.'
    )
  }

  const handleManualSubmit = async (event) => {
    event.preventDefault()
    if (!manualSession || manualSubmitting) return

    const selectedVisitType = manualVisitType || manualSession.visitType || 'initial'
    const visitTypeChanged = selectedVisitType !== manualOriginalVisitType
    const filled = getChangedManualAnswers(manualSession, manualTexts, manualOriginalTexts, selectedVisitType)
    if (!filled.length && !visitTypeChanged) {
      setManualStatus('새로 입력하거나 수정한 문진 내용이 없습니다.')
      return
    }

    setManualSubmitting(true)
    setManualStatus('직원 입력을 저장하고 있습니다.')
    try {
      let sessionForProcessing = manualSession
      if (visitTypeChanged) {
        sessionForProcessing = await updateIntakeSession(manualSession.sessionId, {
          visit_type: selectedVisitType,
          question_set_id: manualSession.questionSetId || 'default',
        })
      }
      for (const { question, transcript } of filled) {
        await processTranscript({
          sessionId: manualSession.sessionId,
          questionId: question.id,
          questionType: question.question_type,
          questionText: questionTextForBackend(question),
          questionSetId: sessionForProcessing?.questionSetId || manualSession.questionSetId || 'default',
          visitType: selectedVisitType,
          transcript,
          role: 'staff',
        })
      }
      await loadSessions()
      closeManualInput()
    } catch (error) {
      console.error('manual intake failed:', error)
      setManualStatus('저장 중 오류가 발생했습니다. 네트워크와 백엔드 상태를 확인해 주세요.')
    } finally {
      setManualSubmitting(false)
    }
  }

  return (
    <div className="reception-page">
      <header className="reception-header">
        <div>
          <p className="rp-eyebrow">접수 데스크</p>
          <div className="rp-brand-lockup">
            <img className="rp-logo-svg" src={logoUrl} alt="" aria-hidden="true" />
            <h1>문진톡톡</h1>
          </div>
        </div>
        <div className="rp-stats">
          <div>
            <span>{sessions.length}</span>
            <small>오늘 접수</small>
          </div>
          <div>
            <span>{waitingCount}</span>
            <small>문진 대기</small>
          </div>
        </div>
      </header>

      <div className="reception-grid">
        <ReceptionForm
          form={form}
          created={created}
          updateField={updateField}
          onSubmit={handleSubmit}
          onOpenTablet={(sessionId, patientToken) => navigate(sessionUrl(`/patient/${sessionId}`, patientToken))}
          submitError={formError}
          isSubmitting={isCreatingSession}
        />
        <ReceptionSessionList sessions={sessions} onOpenManualInput={openManualInput} onDeleteSession={handleDeleteSession} />
      </div>

      <ReceptionManualInput
        session={manualSession}
        manualTexts={manualTexts}
        manualStatus={manualStatus}
        manualVisitType={manualVisitType}
        submitting={manualSubmitting}
        updateManualText={updateManualText}
        onVisitTypeChange={handleManualVisitTypeChange}
        onSubmit={handleManualSubmit}
        onClose={closeManualInput}
      />
    </div>
  )
}

function makeManualTextState(session, visitType = session.visitType || 'initial') {
  const responses = session.responses || {}
  return Object.fromEntries(
    (QUESTIONS[visitType] || QUESTIONS.initial).map((question) => [
      question.id,
      responses[question.id]?.text || responses[question.id]?.transcript || '',
    ])
  )
}

function getChangedManualAnswers(session, manualTexts, originalTexts, visitType = session.visitType || 'initial') {
  const questions = QUESTIONS[visitType] || QUESTIONS.initial
  return questions
    .map((question) => ({ question, transcript: (manualTexts[question.id] || '').trim() }))
    .filter((item) => item.transcript && item.transcript !== (originalTexts[item.question.id] || '').trim())
}
