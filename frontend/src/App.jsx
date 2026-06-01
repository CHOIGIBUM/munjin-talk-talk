import { useEffect, useMemo, useState } from 'react'
import { Link, Routes, Route, useLocation } from 'react-router-dom'
import PatientFlow from './components/patient/PatientFlow.jsx'
import PatientKioskView from './components/patient/PatientKioskView.jsx'
import DoctorView from './components/doctor/DoctorView.jsx'
import DoctorQueueView from './components/doctor/DoctorQueueView.jsx'
import PatientGuideScreen from './components/patient/PatientGuideScreen.jsx'
import ReceptionView from './components/staff/ReceptionView.jsx'
import { getDoctorQueue, isMockApiEnabled } from './services/api.js'

// 앱의 최상위 라우터입니다.
// 접수처, 환자 태블릿, 의사 대기열, 원페이퍼, 안내문 화면을 URL 단위로 나누고
// 상단 메뉴가 현재 세션 상태에 맞는 화면으로 이동하도록 연결합니다.

// v4 변경:
// - 우측 상단에 시연용 Flag 메뉴 (드롭다운)
// - 초진/재진/위험 분기 강제 트리거 시연 가능
// - 환자 화면(/)에서만 표시

export default function App() {
  const [sessions, setSessions] = useState([])
  const location = useLocation()
  const mockMode = isMockApiEnabled()

  // 대기열 숫자와 상단 메뉴 이동 대상은 세션 상태가 바뀌면 계속 새로고침합니다.
  // 로컬 목업은 storage event를, 운영 환경은 주기적 API 조회를 사용합니다.
  useEffect(() => {
    const refresh = async () => setSessions(await getDoctorQueue())
    refresh()
    window.addEventListener('storage', refresh)
    window.addEventListener('munjin-demo-sessions', refresh)
    const timer = setInterval(refresh, 5000)
    return () => {
      window.removeEventListener('storage', refresh)
      window.removeEventListener('munjin-demo-sessions', refresh)
      clearInterval(timer)
    }
  }, [])

  // 아무 세션도 없을 때는 환자 태블릿/원페이퍼/안내문 메뉴를 비활성화하고,
  // 세션이 생기면 가장 자연스러운 대상 세션으로 메뉴 링크를 잡습니다.
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
        <Link to="/staff" className={navClass(path === '/staff')}>
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
          <Route path="/" element={mockMode ? <PatientFlowWithDemoMenu /> : <ReceptionView />} />
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


// 환자 화면에 시연 메뉴를 감싸는 래퍼
// API 없이 화면만 시연할 때 쓰는 환자 플로우 데모 래퍼입니다.
// 운영 라우팅에서는 접수처에서 만든 sessionId 기반 화면을 사용합니다.
function PatientFlowWithDemoMenu() {
  const [demoConfig, setDemoConfig] = useState({
    visitType: null,           // null=시작화면부터, 'initial'/'followup'
    forceFlagAtQ: null         // null/'Q1'/'Q2'/'Q3'
  })
  const [key, setKey] = useState(0)  // 시나리오 변경 시 PatientFlow 강제 리마운트

  const handleScenario = (visitType, forceFlagAtQ) => {
    setDemoConfig({ visitType, forceFlagAtQ })
    setKey(k => k + 1)
  }

  return (
    <>
      <DemoMenu onScenario={handleScenario} current={demoConfig} />
      <PatientFlow
        key={key}
        initialVisitType={demoConfig.visitType}
        forceFlagAtQ={demoConfig.forceFlagAtQ}
      />
    </>
  )
}


function DemoMenu({ onScenario, current }) {
  const [open, setOpen] = useState(false)

  const scenarios = [
    { label: '처음부터 시작', visitType: null, force: null },
    { label: '초진 — 정상',   visitType: 'initial', force: null },
    { label: '재진 — 정상',   visitType: 'followup', force: null },
    { label: '재진 — 객혈 분기 (Q3에서 위험 발생)', visitType: 'followup', force: 'Q3' },
  ]

  return (
    <div className="demo-menu">
      <button
        type="button"
        className="demo-menu-trigger"
        onClick={() => setOpen(o => !o)}
      >
        🎬 시연 시나리오 ▾
      </button>
      {open && (
        <div className="demo-menu-dropdown">
          <div className="demo-menu-header">시연 케이스 선택</div>
          {scenarios.map((s, i) => (
            <button
              key={i}
              type="button"
              className="demo-menu-item"
              onClick={() => {
                onScenario(s.visitType, s.force)
                setOpen(false)
              }}
            >
              {s.label}
            </button>
          ))}
          <div className="demo-menu-note">
            ※ 시연용 메뉴. 실 운영에서는 제거됨.
          </div>
        </div>
      )}
    </div>
  )
}
