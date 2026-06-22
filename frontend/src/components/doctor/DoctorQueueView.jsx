import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDoctorQueue } from '../../services/api.js'
import './DoctorQueueView.css'

// 의사 대기열 화면입니다.
// 환자 문진 완료 직후에는 analysis_pending으로 올라오고,
// 백그라운드 분석이 끝나면 waiting_doctor 상태로 전환됩니다.
const statusLabel = {
  waiting_tablet: '문진 대기',
  in_progress: '문진 진행 중',
  staff_help: '직원 도움 요청',
  analysis_pending: 'AI 분석 중',
  waiting_doctor: '의사 확인 대기',
  analysis_failed: '분석 재실행 필요',
  completed: '의사 확인 대기',
  needs_priority: '우선 확인 필요',
  reviewed: '응답·안내 완료',
}

export default function DoctorQueueView() {
  const [sessions, setSessions] = useState([])

  useEffect(() => {
    const refresh = async () => {
      try {
        setSessions(await getDoctorQueue())
      } catch (error) {
        console.error('doctor queue refresh failed:', error)
        setSessions([])
      }
    }
    refresh()
    const timer = setInterval(refresh, 4000)
    return () => clearInterval(timer)
  }, [])

  const sorted = useMemo(() => {
    const priority = {
      needs_priority: 0,
      waiting_doctor: 1,
      completed: 1,
      analysis_failed: 2,
      analysis_pending: 3,
      in_progress: 4,
      staff_help: 5,
      waiting_tablet: 6,
      reviewed: 7,
    }
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
