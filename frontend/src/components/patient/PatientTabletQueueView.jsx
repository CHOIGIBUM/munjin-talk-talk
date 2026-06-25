import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import logoUrl from '../../assets/munjin-logo.svg'
import { getDoctorQueue } from '../../services/api.js'
import { sessionUrl } from '../../services/api/client.js'
import { sortTabletQueue } from '../../services/queueOrder.js'
import { useDragScroll } from '../../hooks/useDragScroll.js'
import './PatientKioskView.css'

const TABLET_QUEUE_STATUSES = new Set([
  'waiting_tablet',
  'in_progress',
])

const TABLET_STATUS_LABEL = {
  waiting_tablet: '준비됨',
  in_progress: '진행 중',
}

function actionLabel(status) {
  if (status === 'in_progress') return '이어서 하기'
  return '문진 시작하기'
}

// 여러 태블릿이 같은 주소(/patient)에 접속해도 오늘 문진 대기 환자를 고를 수 있는 화면입니다.
// 실제 문진은 환자별 URL(/patient/:sessionId)로 들어가고, 이 화면은 태블릿용 대기열 역할만 합니다.
export default function PatientTabletQueueView() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const listRef = useDragScroll()

  const loadSessions = useCallback(async () => {
    try {
      const next = await getDoctorQueue({ role: 'staff' })
      setSessions(next)
      setError('')
    } catch (err) {
      console.error('patient tablet queue refresh failed:', err)
      setError('문진 대기열을 불러오지 못했습니다. 네트워크 상태를 확인해 주세요.')
      setSessions([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSessions()
    const timer = setInterval(loadSessions, 5000)
    return () => clearInterval(timer)
  }, [loadSessions])

  const waitingSessions = useMemo(
    () => sortTabletQueue(sessions.filter((session) => TABLET_QUEUE_STATUSES.has(session.status))),
    [sessions]
  )

  return (
    <section className="tablet-queue-page">
      <header className="tablet-queue-header">
        <div className="tablet-queue-brand">
          <img src={logoUrl} alt="" aria-hidden="true" />
          <div>
            <p>문진톡톡</p>
            <h1>문진 시작하기</h1>
          </div>
        </div>
        <button type="button" onClick={loadSessions}>새로고침</button>
      </header>

      <div className="tablet-queue-panel">
        <div className="tablet-queue-title">
          <h2>성함을 확인하고 눌러 주세요</h2>
          <span>{waitingSessions.length}명</span>
        </div>

        {error && <p className="tablet-queue-error">{error}</p>}
        {loading && <p className="tablet-queue-empty">문진 준비 상태를 확인하고 있습니다.</p>}

        {!loading && !waitingSessions.length && (
          <div className="tablet-queue-empty">
            <strong>아직 준비된 문진이 없습니다</strong>
            <p>접수 직원이 준비해 드리면 이곳에 성함이 표시됩니다.</p>
            <p>직원 도움이 필요한 문진은 접수 화면에서 따로 확인합니다.</p>
            <p>잠시만 기다려 주세요.</p>
          </div>
        )}

        <div className="tablet-queue-list drag-scroll-region" ref={listRef}>
          {waitingSessions.map((session) => (
            <article key={session.sessionId} className={`tablet-queue-card ${session.status}`}>
              <div>
                <span className="tablet-queue-badge">
                  {TABLET_STATUS_LABEL[session.status] || session.status}
                </span>
                <h3>{session.patient.name} 어르신</h3>
                <p>
                  #{session.patient.receiptId} · {session.patient.age}세 {session.patient.gender}
                  {' · '}
                  {session.visitType === 'followup' ? '재진' : '초진'}
                </p>
              </div>
              <Link to={sessionUrl(`/patient/${encodeURIComponent(session.sessionId)}`, session.patientToken)}>
                {actionLabel(session.status)}
              </Link>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
