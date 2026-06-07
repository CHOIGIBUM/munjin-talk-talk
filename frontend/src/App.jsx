import { useEffect, useMemo, useState } from 'react'
import { Link, Routes, Route, useLocation } from 'react-router-dom'
import PatientKioskView from './components/patient/PatientKioskView.jsx'
import DoctorView from './components/doctor/DoctorView.jsx'
import DoctorQueueView from './components/doctor/DoctorQueueView.jsx'
import PatientGuideScreen from './components/patient/PatientGuideScreen.jsx'
import ReceptionView from './components/staff/ReceptionView.jsx'
import { getDoctorQueue } from './services/api.js'

// 앱의 최상위 라우터입니다.
// 실제 운영 흐름은 접수처에서 세션을 만들고, 그 sessionId로 태블릿/원페이퍼/안내문을 여는 구조입니다.
export default function App() {
  const [sessions, setSessions] = useState([])
  const location = useLocation()

  // 상단 메뉴는 실제 백엔드 대기열을 주기적으로 읽어 가장 자연스러운 세션으로 이동시킵니다.
  useEffect(() => {
    const refresh = async () => {
      try {
        setSessions(await getDoctorQueue())
      } catch (error) {
        console.error('queue refresh failed:', error)
        setSessions([])
      }
    }
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [])

  const navTargets = useMemo(() => {
    const tablet = sessions.find((session) => session.status === 'waiting_tablet')
      || sessions.find((session) => session.status === 'in_progress')
      || sessions[0]
    const doctor = sessions.find((session) => ['needs_priority', 'completed', 'reviewed'].includes(session.status))
      || tablet
    return {
      patient: tablet ? `/patient/${tablet.sessionId}` : null,
      doctor: doctor ? `/doctor/${doctor.sessionId}` : null,
      guide: doctor ? `/guide/${doctor.sessionId}` : null,
    }
  }, [sessions])

  const path = location.pathname
  const navClass = (active) => (active ? 'active' : '')

  return (
    <>
      <nav className="mode-switcher">
        <Link to="/staff" className={navClass(path === '/staff' || path === '/')}>
          직원 접수
        </Link>
        <NavItem to={navTargets.patient} active={path.startsWith('/patient/')} label="환자 태블릿" />
        <Link to="/doctor/queue" className={navClass(path === '/doctor/queue')}>
          의사 대기열
        </Link>
        <NavItem
          to={navTargets.doctor}
          active={path.startsWith('/doctor/') && path !== '/doctor/queue'}
          label="원페이퍼"
        />
        <NavItem to={navTargets.guide} active={path.startsWith('/guide/')} label="안내문 출력" />
      </nav>

      <main className="app-stage">
        <Routes>
          <Route path="/" element={<ReceptionView />} />
          <Route path="/staff" element={<ReceptionView />} />
          <Route path="/patient/:sessionId" element={<PatientKioskView />} />
          <Route path="/doctor/queue" element={<DoctorQueueView />} />
          <Route path="/doctor" element={<DoctorView />} />
          <Route path="/doctor/:sessionId" element={<DoctorView />} />
          <Route path="/guide" element={<PatientGuideScreen />} />
          <Route path="/guide/:sessionId" element={<PatientGuideScreen />} />
        </Routes>
      </main>
    </>
  )
}

function NavItem({ to, active, label }) {
  if (!to) {
    return (
      <span className="disabled" aria-disabled="true" title="문진 세션 생성 후 사용할 수 있습니다.">
        {label}
      </span>
    )
  }
  return (
    <Link to={to} className={active ? 'active' : ''}>
      {label}
    </Link>
  )
}
