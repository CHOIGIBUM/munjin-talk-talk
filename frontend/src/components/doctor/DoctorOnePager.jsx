import { useState, useEffect, useMemo } from 'react'
import { getOnePager } from '../../services/api.js'
import { normalizeOnePager } from '../../services/onepagerAdapter.js'
import { CheckIcon, ClueChip, CopyIcon, clueKey, getCluesForSlot, getUnlinkedClues } from './DoctorOnePagerParts.jsx'
import './DoctorOnePager.css'

function getOnePagerStatusMessage(status) {
  const messages = {
    refreshing: '원페이퍼를 새로 불러오는 중입니다.',
    reviewing: '원페이퍼 최종 검토를 갱신하고 있습니다.',
    refreshed: '최신 원페이퍼가 반영되었습니다.',
    reviewed: '원페이퍼 검토가 갱신되었습니다.',
    error: '요청 처리에 실패했습니다. 잠시 후 다시 시도해 주세요.',
    retrying: '문진 분석을 다시 실행하고 있습니다.',
    queued: '문진 분석이 대기열에 등록되었습니다.',
  }
  return messages[status] || ''
}

// 의사가 실제로 보는 원페이퍼 본문입니다.
// 백엔드 onepager JSON을 받아 증상, 문진 맥락, 확인 항목, EMR 문장을 한 화면에 배치합니다.

// v4 변경:
// - "진단명 추천 없음" / "검증 완료" 자잘한 chips 제거
// - 의료진 확인 항목 체크박스 실제 작동 (클릭 시 체크 + 파란 테두리)
// - 재진의 변화 추적 카드를 "오늘 말한 불편함" 디자인으로 변경
//   (EMR 연동 안 되므로 이전 진료 추적 불가, 환자가 새로 말한 증상 그대로 표시)
// - 좌우 패널 길이 차이로 무너지지 않도록 균형 조정
// - "위험 — 우선 평가 필요" amber 배지는 실제 safety flag가 있을 때만 표시

export default function DoctorOnePager({
  sessionId,
  sessionData,
  sidePanel,
  renderAgenda = true,
  onRefresh,
  onAiReview,
  onAnalysisRetry,
  onepagerStatus,
}) {
  const [apiData, setApiData] = useState(null)
  const [copied, setCopied] = useState(false)
  const [checked, setChecked] = useState({})  // {0: true, 2: true} 형태

  // sessionData가 직접 내려오지 않으면 sessionId로 onepager를 조회합니다.
  useEffect(() => {
    if (sessionData || !sessionId) return
    getOnePager(sessionId).then(setApiData)
  }, [sessionId, sessionData])

  // 화면은 항상 normalizeOnePager 결과만 사용합니다.
  // 백엔드 원본 구조 변화는 onepagerAdapter에서 흡수합니다.
  const data = useMemo(() => {
    const source = sessionData || apiData
    return source ? normalizeOnePager(source) : null
  }, [sessionData, apiData])

  // 세션이 바뀌면 이전 체크 상태가 섞이지 않게 초기화합니다.
  useEffect(() => {
    setChecked({})
  }, [sessionId, sessionData])

  if (!data) {
    return (
      <div className="onepaper-v4 onepaper-empty">
        <div className="op-card">
          <div className="op-card-title">
            <h4>원페이퍼를 표시할 세션이 없습니다</h4>
          </div>
          <p>직원 접수에서 문진 세션을 생성하고 환자 문진을 완료하면 이 화면에 내용이 표시됩니다.</p>
        </div>
      </div>
    )
  }

  const isFollowup = data.patient.visit_type === 'followup'
  const themeClass = isFollowup ? 'theme-followup' : 'theme-initial'
  const symptomSlots = data.symptomSlots || []
  const clinicalClues = data.clinicalClues || []
  const unlinkedClues = getUnlinkedClues(symptomSlots, clinicalClues)
  const patientQuestionnaire = data.patientQuestionnaire || []
  const analysisStatus = data.analysis?.status || ''
  const isAnalysisPending = ['pending', 'running'].includes(analysisStatus)
  const isAnalysisFailed = ['failed', 'enqueue_failed', 'analysis_failed'].includes(analysisStatus) || data.status === 'analysis_failed'
  const statusNotice = getOnePagerStatusMessage(onepagerStatus)

  // EMR 복사용 문장을 클립보드에 복사합니다.
  const handleCopy = () => {
    navigator.clipboard?.writeText(data.transferText)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const toggleCheck = (idx) => {
    setChecked(prev => ({ ...prev, [idx]: !prev[idx] }))
  }

  return (
    <div className={`onepaper-v4 ${themeClass}`}>
      {statusNotice && (
        <div className={`op-slide-toast ${onepagerStatus}`}>
          <span>{statusNotice}</span>
        </div>
      )}

      {(isAnalysisPending || isAnalysisFailed) && (
        <div className={`op-analysis-banner ${isAnalysisFailed ? 'failed' : 'pending'}`}>
          <div>
            <b>{isAnalysisFailed ? '문진 분석을 다시 실행해 주세요' : '문진 분석 중입니다'}</b>
            <p>
              {isAnalysisFailed
                ? '환자 문진은 완료되었습니다. 저장된 원문으로 분석을 다시 실행하거나 수동으로 확인할 수 있습니다.'
                : '환자 문진은 완료되었습니다. 원페이퍼가 준비되면 새로고침 후 확인해 주세요.'}
            </p>
            {data.analysis?.error && <small>{data.analysis.error}</small>}
          </div>
          <div className="op-analysis-actions">
            {onRefresh && (
              <button type="button" className="op-tool-btn" onClick={onRefresh}>
                새로고침
              </button>
            )}
            {isAnalysisFailed && onAnalysisRetry && (
              <button type="button" className="op-tool-btn op-tool-btn-primary" onClick={onAnalysisRetry}>
                입력 기반 재분석
              </button>
            )}
          </div>
        </div>
      )}

      {/* 위험 플래그 */}
      {data.safety_flag && data.safety_flag.severity === 'high' && (
        <div className="op-safety-alert">
          <span className="osa-icon">⚠</span>
          <div>
            <b>{data.safety_flag.label} — 우선 평가 필요</b>
            <p>{data.safety_flag.message || `감지: "${data.safety_flag.matched_pattern}" (${data.safety_flag.category})`}</p>
          </div>
        </div>
      )}

      {/* 환자 정보 바 — "진단명 추천 없음" / "검증 완료" 제거 */}
      <div className="op-patient-bar">
        <div className="op-patient-info">
          <h4>
            {data.patient.name} · {data.patient.age}세 {data.patient.gender} · {data.patient.department}
          </h4>
          <p>
            <span className={`op-visit-badge ${data.patient.visit_type}`}>
              {isFollowup ? '재진' : '초진'}
            </span>
          </p>
        </div>
        {!isAnalysisPending && !isAnalysisFailed && (onRefresh || onAiReview) && (
          <div className="op-toolbar">
            {onRefresh && (
              <button
                type="button"
                className="op-tool-btn"
                onClick={onRefresh}
                disabled={onepagerStatus === 'refreshing' || onepagerStatus === 'reviewing' || onepagerStatus === 'retrying'}
              >
                새로고침
              </button>
            )}
            {onAiReview && (
              <button
                type="button"
                className="op-tool-btn op-tool-btn-primary"
                onClick={onAiReview}
                disabled={onepagerStatus === 'refreshing' || onepagerStatus === 'reviewing' || onepagerStatus === 'retrying'}
              >
                검토 갱신
              </button>
            )}
          </div>
        )}
      </div>

      {(isAnalysisPending || isAnalysisFailed) && (
        <section className={`op-card op-analysis-lock-card ${isAnalysisFailed ? 'failed' : 'pending'}`}>
          <h4>{isAnalysisFailed ? '분석을 다시 실행해야 합니다' : '원페이퍼 생성 중입니다'}</h4>
          <p>
            {isAnalysisFailed
              ? '환자 문진 원문은 저장되어 있습니다. 분석 다시 실행 후 원페이퍼를 확인해 주세요.'
              : '아직 의료진 확인용 문서가 완성되지 않았습니다. 잠시 후 상태 새로고침을 눌러 주세요.'}
          </p>
        </section>
      )}

      {/* 좌우 분할 */}
      <div className={`op-split ${isAnalysisPending || isAnalysisFailed ? 'op-split-locked' : ''}`}>

        {/* 좌측 3카드 */}
        <div className="op-left">

          {/* 카드 1: 증상 슬롯 + 증상별 맥락 단서 */}
          <section className="op-card symptom-card">
            <div className="op-card-title">
              <h4>오늘 말한 불편함</h4>
              <span className={`op-chip ${isFollowup ? 'teal' : 'blue'}`}>
                {isFollowup ? '재진' : '초진'}
              </span>
            </div>

            {symptomSlots.length > 0 ? (
              <div className="slot-rows">
                {symptomSlots.map((slot, i) => {
                  const slotClues = getCluesForSlot(slot, clinicalClues)
                  return (
                    <div key={i} className={`slot-row ${slot.alert ? 'slot-row-alert' : ''}`}>
                      <div className="slot-name">
                        {slot.name} <small>({slot.sub})</small>
                      </div>
                      <div className={`slot-match-badge ${slot.alert ? 'slot-match-badge-alert' : ''}`}>
                        {slot.alert ? '우선 확인' : '매칭됨'}
                      </div>
                      {slot.sourceQuote && <div className="slot-quote">"{slot.sourceQuote}"</div>}
                      {slotClues.length > 0 && (
                        <div className="slot-clues">
                          {slotClues.map((clue) => (
                            <ClueChip key={clueKey(clue)} clue={clue} />
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="slot-empty">직접 매칭된 증상 슬롯은 없습니다.</div>
            )}

            {unlinkedClues.length > 0 && (
              <div className="context-strip">
                <div className="context-strip-title">문진 맥락</div>
                <div className="context-strip-items">
                  {unlinkedClues.map((clue) => (
                    <ClueChip key={clueKey(clue)} clue={clue} />
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* 카드 2: 의료진 확인 항목 — 체크박스 실제 작동 */}
          <section className="op-card review-card">
            <div className="op-card-title">
              <h4>{isFollowup ? '재진 확인 항목' : '의료진 확인 항목'}</h4>
              <span className="op-chip gray">체크용</span>
            </div>
            <ul className="check-list-v4">
              {data.reviewItems.map((item, i) => {
                const isPriority = item.startsWith('[우선]')
                const isChecked = !!checked[i]
                return (
                  <li
                    key={i}
                    className={[
                      'check-item-v4',
                      isPriority && 'check-priority',
                      isChecked && 'check-checked'
                    ].filter(Boolean).join(' ')}
                    onClick={() => toggleCheck(i)}
                  >
                    <span className={`check-box-v4 ${isChecked ? 'checked' : ''}`}>
                      {isChecked && <CheckIcon />}
                    </span>
                    <span className="check-text-v4">{item}</span>
                  </li>
                )
              })}
            </ul>
          </section>

          {/* 카드 3: 환자 원문 확인용 문진 요약 + EMR 복사용 초안 */}
          <section className="op-card transfer-card">
            <div className="op-card-title">
              <h4>환자 문진 요약</h4>
              <span className="op-chip teal">원문 확인</span>
            </div>
            {patientQuestionnaire.length > 0 ? (
              <div className="patient-summary-list">
                {patientQuestionnaire.map(item => (
                  <div className="patient-summary-row" key={item.id}>
                    <div className="patient-summary-head">{item.label}</div>
                    {item.original && (
                      <div className="patient-summary-original">
                        <span>원문</span>
                        <p>"{item.original}"</p>
                      </div>
                    )}
                    {item.standardized && (
                      <div className="patient-summary-standard">
                        <span>표준화</span>
                        <p>{item.standardized}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="transfer-text">환자 문진 원문이 아직 표시되지 않았습니다.</p>
            )}

            {data.transferText && (
              <div className="emr-draft-box">
                <div className="emr-draft-title">
                  <span>EMR 복사용 초안</span>
                  <button className="copy-btn compact" onClick={handleCopy}>
                    <CopyIcon />
                    {copied ? '복사됨!' : 'EMR로 복사'}
                  </button>
                </div>
                <p className="transfer-text">{data.transferText}</p>
              </div>
            )}
          </section>
        </div>

        {/* 우측 패널 */}
        <aside className="op-right">
          {sidePanel}
        </aside>
      </div>
    </div>
  )
}
