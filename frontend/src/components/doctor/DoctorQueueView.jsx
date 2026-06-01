import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDoctorQueue } from '../../services/api.js'
import './DoctorQueueView.css'

const statusLabel = {
  waiting_tablet: '문진 대기',
  in_progress: '문진 진행중',
  staff_help: '직원 도움 요청',
  completed: '의사 답변 대기',
  needs_priority: '우선 확인 필요',
  reviewed: '답변·안내 완료',
}

export default function DoctorQueueView() {
  const [sessions, setSessions] = useState([])

  useEffect(() => {
    const refresh = async () => setSessions(await getDoctorQueue())
    refresh()
    window.addEventListener('storage', refresh)
    window.addEventListener('munjin-demo-sessions', refresh)
    const timer = setInterval(refresh, 4000)
    return () => {
      window.removeEventListener('storage', refresh)
      window.removeEventListener('munjin-demo-sessions', refresh)
      clearInterval(timer)
    }
  }, [])

  const sorted = useMemo(() => {
    const priority = { needs_priority: 0, completed: 1, in_progress: 2, staff_help: 3, waiting_tablet: 4, reviewed: 5 }
    return [...sessions].sort((a, b) => {
      const pa = priority[a.status] ?? 9
      const pb = priority[b.status] ?? 9
      if (pa !== pb) return pa - pb
      return (a.queueNumber || 0) - (b.queueNumber || 0)
    })
  }, [sessions])

  return (
    <div className="doctor-queue-page">
      <header className="dq-header">
        <div>
          <p>의사 대기열</p>
          <h1>오늘 문진 환자 대기열</h1>
        </div>
        <Link to="/staff">접수 화면</Link>
      </header>

      <div className="dq-board">
        {sorted.map((session) => (
          <article key={session.sessionId} className={`dq-row ${session.risk === 'high' ? 'risk' : ''}`}>
            <div className="dq-num">{session.queueNumber}</div>
            <div className="dq-main">
              <div className="dq-name">
                <strong>{session.patient.name}</strong>
                <span>{session.visitType === 'initial' ? '초진' : '재진'}</span>
                {session.risk === 'high' && <mark>우선</mark>}
              </div>
              <p>
                {session.patient.age}세 {session.patient.gender} · {session.patient.department} · #{session.patient.receiptId}
              </p>
            </div>
            <span className={`dq-status ${session.status}`}>{statusLabel[session.status] || session.status}</span>
            <div className="dq-actions">
              <Link to={`/doctor/${session.sessionId}`}>원페이퍼</Link>
              <Link to={`/guide/${session.sessionId}`}>안내문</Link>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
