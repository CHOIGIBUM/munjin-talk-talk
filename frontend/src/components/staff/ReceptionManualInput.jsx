import { Link } from 'react-router-dom'
import { QUESTIONS } from '../../config/questions.js'

// 환자가 태블릿 문진을 마치지 못했을 때 직원이 같은 문항 구조로 대신 입력하는 패널입니다.
export default function ReceptionManualInput({
  session,
  manualTexts,
  manualStatus,
  manualVisitType,
  submitting,
  updateManualText,
  onVisitTypeChange,
  onSubmit,
  onClose,
}) {
  if (!session) return null

  const selectedVisitType = manualVisitType || session.visitType || 'initial'
  const questions = QUESTIONS[selectedVisitType] || QUESTIONS.initial

  return (
    <section className="rp-panel rp-manual-panel" aria-live="polite">
      <div className="rp-panel-title">
        <div>
          <h2>직원 대리 문진 입력</h2>
          <span>
            {session.patient.name} · #{session.patient.receiptId} · {selectedVisitType === 'initial' ? '초진' : '재진'}
          </span>
        </div>
        <button className="rp-ghost" type="button" onClick={onClose}>닫기</button>
      </div>

      <form className="rp-manual-form" onSubmit={onSubmit}>
        <div className="rp-manual-visit-switch" role="group" aria-label="문진 유형 선택">
          <button
            type="button"
            className={selectedVisitType === 'initial' ? 'active' : ''}
            onClick={() => onVisitTypeChange('initial')}
          >
            초진
          </button>
          <button
            type="button"
            className={selectedVisitType === 'followup' ? 'active' : ''}
            onClick={() => onVisitTypeChange('followup')}
          >
            재진
          </button>
        </div>

        {questions.map((question) => (
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
            <Link to={`/doctor/${session.sessionId}`}>원페이퍼 열기</Link>
            <button type="submit" disabled={submitting}>
              {submitting ? '저장 중' : '직원 입력 저장'}
            </button>
          </div>
        </div>
      </form>
    </section>
  )
}
