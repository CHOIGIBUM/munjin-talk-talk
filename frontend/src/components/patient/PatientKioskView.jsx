import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import PatientFlow from './PatientFlow.jsx'
import { getIntakeSession, isRemoteApiEnabled, requestStaffHelp } from '../../services/api.js'
import {
  markSessionCompleted,
  markStaffRequested,
  saveTranscriptAnswer,
} from '../../services/demoSessions.js'
import './PatientKioskView.css'

// 접수처에서 만든 sessionId를 받아 실제 환자 태블릿 문진을 시작하는 화면입니다.
// 운영 모드에서는 백엔드 세션을, 목업 모드에서는 localStorage 세션을 사용합니다.
export default function PatientKioskView() {
  const { sessionId } = useParams()
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  // URL의 sessionId로 환자 정보와 초진/재진 설정을 불러옵니다.
  useEffect(() => {
    let active = true
    setLoading(true)
    getIntakeSession(sessionId).then((next) => {
      if (active) setSession(next)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => {
      active = false
    }
  }, [sessionId])

  if (loading) {
    return (
      <div className="kiosk-missing">
        <h1>문진 세션을 불러오는 중입니다</h1>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="kiosk-missing">
        <h1>문진 세션을 찾을 수 없습니다</h1>
        <p>접수 데스크에서 환자 확인 후 새 문진 세션을 생성해 주세요.</p>
        <Link to="/staff">접수 화면으로 이동</Link>
      </div>
    )
  }

  return (
    <PatientFlow
      sessionId={session.sessionId}
      patient={session.patient}
      queueNumber={session.queueNumber}
      initialVisitType={session.visitType}
      frameVariant="device"
      skipVisitTypeWhenPreset={false}
      onTranscriptConfirmed={(answer) => {
        // 운영 모드에서는 processTranscript가 이미 백엔드 저장까지 수행합니다.
        // 목업 모드에서만 localStorage에 답변을 저장합니다.
        if (!isRemoteApiEnabled()) saveTranscriptAnswer(session.sessionId, answer)
      }}
      onStaffCallRequest={() => {
        if (isRemoteApiEnabled()) requestStaffHelp(session.sessionId)
        else markStaffRequested(session.sessionId)
      }}
      onComplete={() => {
        if (!isRemoteApiEnabled()) markSessionCompleted(session.sessionId)
      }}
    />
  )
}
