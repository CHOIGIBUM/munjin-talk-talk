import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createIntakeSession, getDoctorQueue, getIntakeSession, processTranscript } from '../../services/api.js'
import { QUESTIONS } from '../../config/questions.js'
import logoUrl from '../../assets/munjin-logo.svg'
import './ReceptionView.css'

const INITIAL_FORM = {
  fullName: '최영자',
  birthDate: '1950-09-17',
  gender: '여성',
  receiptId: '',
  department: '이비인후과',
  doctor: '이민우',
  phone: '',
  visitType: 'initial',
}

const statusLabel = {
  waiting_tablet: '문진 대기',
  in_progress: '문진 진행중',
  staff_help: '직원 도움 요청',
  completed: '의사 답변 대기',
  needs_priority: '우선 확인 필요',
  reviewed: '답변·안내 완료',
}

const manualInputStatuses = new Set(['staff_help', 'needs_priority', 'in_progress', 'waiting_tablet'])

function formatPhone(value) {
  const digits = String(value || '').replace(/\D/g, '').slice(0, 11)
  if (digits.length <= 3) return digits
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`
}

export default function ReceptionView() {
  const navigate = useNavigate()
  const [form, setForm] = useState(INITIAL_FORM)
  const [sessions, setSessions] = useState([])
  const [created, setCreated] = useState(null)
  const [manualSession, setManualSession] = useState(null)
  const [manualTexts, setManualTexts] = useState({})
  const [manualOriginalTexts, setManualOriginalTexts] = useState({})
  const [manualStatus, setManualStatus] = useState('')
  const [manualSubmitting, setManualSubmitting] = useState(false)

  const loadSessions = useCallback(async () => {
    setSessions(await getDoctorQueue())
  }, [])

  useEffect(() => {
    loadSessions()
    window.addEventListener('storage', loadSessions)
    window.addEventListener('munjin-demo-sessions', loadSessions)
    const timer = setInterval(loadSessions, 5000)
    return () => {
      window.removeEventListener('storage', loadSessions)
      window.removeEventListener('munjin-demo-sessions', loadSessions)
      clearInterval(timer)
    }
  }, [loadSessions])

  const waitingCount = useMemo(
    () => sessions.filter((session) => ['waiting_tablet', 'in_progress', 'staff_help'].includes(session.status)).length,
    [sessions]
  )

  const updateField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const openManualInput = async (session) => {
    setManualStatus('문진 내용을 불러오는 중입니다.')
    const detail = await getIntakeSession(session.sessionId)
    const nextSession = detail || session
    const responses = nextSession.responses || {}
    const nextTexts = Object.fromEntries(
      (QUESTIONS[nextSession.visitType] || QUESTIONS.initial).map((question) => [
        question.id,
        responses[question.id]?.text || responses[question.id]?.transcript || '',
      ])
    )
    setManualSession(nextSession)
    setManualTexts(nextTexts)
    setManualOriginalTexts(nextTexts)
    setManualStatus('환자가 말한 내용을 직원이 대신 입력할 수 있습니다.')
  }

  const updateManualText = (questionId, value) => {
    setManualTexts((prev) => ({ ...prev, [questionId]: value }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const next = await createIntakeSession(form)
    await loadSessions()
    setCreated(next)
  }

  const handleManualSubmit = async (event) => {
    event.preventDefault()
    if (!manualSession || manualSubmitting) return

    const questions = QUESTIONS[manualSession.visitType] || QUESTIONS.initial
    const filled = questions
      .map((question) => ({ question, transcript: (manualTexts[question.id] || '').trim() }))
      .filter((item) => item.transcript && item.transcript !== (manualOriginalTexts[item.question.id] || '').trim())

    if (!filled.length) {
      setManualStatus('새로 입력하거나 수정한 문진 내용이 없습니다.')
      return
    }

    setManualSubmitting(true)
    setManualStatus('백엔드 LLM 분석과 검증을 진행하고 있습니다.')
    try {
      for (const { question, transcript } of filled) {
        await processTranscript({
          sessionId: manualSession.sessionId,
          questionId: question.id,
          questionType: question.question_type,
          visitType: manualSession.visitType,
          transcript,
        })
      }
      await loadSessions()
      const refreshed = await getIntakeSession(manualSession.sessionId)
      if (refreshed) setManualSession(refreshed)
      setManualOriginalTexts(manualTexts)
      setManualStatus('직원 입력이 저장되었습니다. 원페이퍼에서 결과를 확인할 수 있습니다.')
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
        <section className="rp-panel">
          <div className="rp-panel-title">
            <h2>신분 확인</h2>
            <span>생년월일 확인 기반</span>
          </div>

          <form className="rp-form" onSubmit={handleSubmit}>
            <label>
              <span>이름</span>
              <input value={form.fullName} onChange={(e) => updateField('fullName', e.target.value)} />
            </label>
            <label>
              <span>생년월일</span>
              <input type="date" value={form.birthDate} onChange={(e) => updateField('birthDate', e.target.value)} />
            </label>
            <label>
              <span>성별</span>
              <select value={form.gender} onChange={(e) => updateField('gender', e.target.value)}>
                <option>여성</option>
                <option>남성</option>
              </select>
            </label>
            <label>
              <span>접수번호</span>
              <input placeholder="비우면 자동 생성" value={form.receiptId} onChange={(e) => updateField('receiptId', e.target.value)} />
            </label>
            <label>
              <span>진료과</span>
              <input value={form.department} onChange={(e) => updateField('department', e.target.value)} />
            </label>
            <label>
              <span>담당 의사</span>
              <input value={form.doctor} onChange={(e) => updateField('doctor', e.target.value)} />
            </label>
            <label className="wide">
              <span>연락처</span>
              <input
                inputMode="numeric"
                placeholder="010-0000-0000"
                value={form.phone}
                onChange={(e) => updateField('phone', formatPhone(e.target.value))}
              />
            </label>

            <div className="rp-segment wide">
              <button
                type="button"
                className={form.visitType === 'initial' ? 'active' : ''}
                onClick={() => updateField('visitType', 'initial')}
              >
                초진
              </button>
              <button
                type="button"
                className={form.visitType === 'followup' ? 'active' : ''}
                onClick={() => updateField('visitType', 'followup')}
              >
                재진
              </button>
            </div>

            <button className="rp-primary wide" type="submit">문진 세션 생성</button>
          </form>

          {created && (
            <div className="rp-created">
              <strong>{created.patient.name} 문진 준비 완료</strong>
              <p>태블릿에서 아래 환자용 URL을 열어 문진을 시작합니다.</p>
              <div className="rp-created-actions">
                <button onClick={() => navigate(`/patient/${created.sessionId}`)}>태블릿 화면 열기</button>
                <Link to={`/doctor/${created.sessionId}`}>원페이퍼 미리보기</Link>
              </div>
            </div>
          )}
        </section>

        <section className="rp-panel">
          <div className="rp-panel-title">
            <h2>오늘 접수</h2>
            <Link to="/doctor/queue">의사 대기열 보기</Link>
          </div>
          <div className="rp-session-list">
            {sessions.map((session) => (
              <article key={session.sessionId} className={`rp-session ${session.risk === 'high' ? 'risk' : ''}`}>
                <div>
                  <strong>{session.patient.name}</strong>
                  <p>
                    #{session.patient.receiptId} · {session.patient.age}세 {session.patient.gender} · {session.visitType === 'initial' ? '초진' : '재진'}
                  </p>
                </div>
                <span className={`rp-status ${session.status}`}>{statusLabel[session.status] || session.status}</span>
                <div className="rp-row-actions">
                  <Link to={`/patient/${session.sessionId}`}>태블릿</Link>
                  <Link to={`/doctor/${session.sessionId}`}>원페이퍼</Link>
                  <Link to={`/guide/${session.sessionId}`}>안내문</Link>
                  {manualInputStatuses.has(session.status) && (
                    <button type="button" onClick={() => openManualInput(session)}>직원 입력</button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>

      {manualSession && (
        <section className="rp-panel rp-manual-panel" aria-live="polite">
          <div className="rp-panel-title">
            <div>
              <h2>직원 대리 문진 입력</h2>
              <span>
                {manualSession.patient.name} · #{manualSession.patient.receiptId} · {manualSession.visitType === 'initial' ? '초진' : '재진'}
              </span>
            </div>
            <button className="rp-ghost" type="button" onClick={() => setManualSession(null)}>닫기</button>
          </div>

          <form className="rp-manual-form" onSubmit={handleManualSubmit}>
            {(QUESTIONS[manualSession.visitType] || QUESTIONS.initial).map((question) => (
              <label key={question.id} className="rp-manual-field">
                <span>
                  <b>{question.badge}</b>
                  {question.title.replace(/\s+/g, ' ')}
                </span>
                <textarea
                  value={manualTexts[question.id] || ''}
                  onChange={(event) => updateManualText(question.id, event.target.value)}
                  placeholder="환자가 말한 내용을 직원이 대신 입력합니다."
                />
              </label>
            ))}

            <div className="rp-manual-footer">
              <p>{manualStatus}</p>
              <div>
                <Link to={`/doctor/${manualSession.sessionId}`}>원페이퍼 열기</Link>
                <button type="submit" disabled={manualSubmitting}>
                  {manualSubmitting ? '저장 중' : '직원 입력 저장'}
                </button>
              </div>
            </div>
          </form>
        </section>
      )}
    </div>
  )
}
