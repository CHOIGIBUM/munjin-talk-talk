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

export default function PatientKioskView() {
  const { sessionId } = useParams()
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

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
