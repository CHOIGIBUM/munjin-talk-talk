import { Link } from 'react-router-dom'
import { MANUAL_INPUT_STATUSES, SESSION_STATUS_LABEL } from './receptionUtils.js'

// 오늘 접수된 환자 목록과 각 세션으로 이동하는 버튼들을 보여줍니다.
export default function ReceptionSessionList({ sessions, onOpenManualInput }) {
  return (
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
            <span className={`rp-status ${session.status}`}>{SESSION_STATUS_LABEL[session.status] || session.status}</span>
            <div className="rp-row-actions">
              <Link to={`/patient/${session.sessionId}`}>태블릿</Link>
              <Link to={`/doctor/${session.sessionId}`}>원페이퍼</Link>
              <Link to={`/guide/${session.sessionId}`}>안내문</Link>
              {MANUAL_INPUT_STATUSES.has(session.status) && (
                <button type="button" onClick={() => onOpenManualInput(session)}>직원 입력</button>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
