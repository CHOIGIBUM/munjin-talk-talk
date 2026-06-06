import { useState, useEffect, useMemo } from 'react'
import { getOnePager, isMockApiEnabled } from '../../services/api.js'
import { normalizeOnePager } from '../../services/onepagerAdapter.js'
import { MOCK_INITIAL, MOCK_FOLLOWUP } from './DoctorOnePager.mocks.js'
import { CheckIcon, ClueChip, CopyIcon, clueKey, getCluesForSlot, getUnlinkedClues } from './DoctorOnePagerParts.jsx'
import './DoctorOnePager.css'

// 의사가 실제로 보는 원페이퍼 본문입니다.
// 백엔드 onepager JSON을 받아 증상, 문진 맥락, 확인 항목, EMR 문장을 한 화면에 배치합니다.

// v4 변경:
// - "진단명 추천 없음" / "검증 완료" 자잘한 chips 제거
// - 의료진 확인 항목 체크박스 실제 작동 (클릭 시 체크 + 파란 테두리)
// - 재진의 변화 추적 카드를 "오늘 말한 불편함" 디자인으로 변경
//   (EMR 연동 안 되므로 이전 진료 추적 불가, 환자가 새로 말한 증상 그대로 표시)
// - 좌우 패널 길이 차이로 무너지지 않도록 균형 조정
// - "위험 — 우선 평가 필요" amber 배지는 유지 (재진 객혈 시연용)

export default function DoctorOnePager({ sessionId, sessionData, sidePanel, renderAgenda = true }) {
  const [apiData, setApiData] = useState(null)
  const [copied, setCopied] = useState(false)
  const [mockOverride, setMockOverride] = useState(null)
  const [checked, setChecked] = useState({})  // {0: true, 2: true} 형태

  // sessionData가 직접 내려오지 않으면 sessionId로 onepager를 조회합니다.
  useEffect(() => {
    if (sessionData || !sessionId) return
    getOnePager(sessionId).then(setApiData)
  }, [sessionId, sessionData])

  // 화면은 항상 normalizeOnePager 결과만 사용합니다.
  // 백엔드 원본 구조 변화는 onepagerAdapter에서 흡수합니다.
  const data = useMemo(() => {
    const fallback = isMockApiEnabled() ? (mockOverride === 'followup' ? MOCK_FOLLOWUP : MOCK_INITIAL) : null
    const source = sessionData || apiData || fallback
    return source ? normalizeOnePager(source, fallback) : null
  }, [sessionData, apiData, mockOverride])

  // mock 변경 시 체크 초기화
  useEffect(() => {
    setChecked({})
  }, [mockOverride])

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

      {/* 데모용 토글 (실시연 시 제거) */}
      {isMockApiEnabled() && !sessionData && !apiData && (
        <div className="onepaper-demo-toggle">
          <button
            className={!mockOverride || mockOverride === 'initial' ? 'active' : ''}
            onClick={() => setMockOverride('initial')}
          >Mock: 초진</button>
          <button
            className={mockOverride === 'followup' ? 'active' : ''}
            onClick={() => setMockOverride('followup')}
          >Mock: 재진 (위험 분기)</button>
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
            <span>접수 {data.patient.receivedAt}</span>
            <span className="op-dot" />
            <span>음성 {data.patient.audioDuration}초</span>
          </p>
        </div>
        {/* "진단명 추천 없음" / "검증 완료" chips 제거됨 */}
      </div>

      {/* 좌우 분할 */}
      <div className="op-split">

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

          {/* 카드 3: 기록용 문장 */}
          <section className="op-card transfer-card">
            <div className="op-card-title">
              <h4>기록용 문장</h4>
              <span className="op-chip teal">EMR 복사</span>
            </div>
            <p className="transfer-text">{data.transferText}</p>
            <button className="copy-btn" onClick={handleCopy}>
              <CopyIcon />
              {copied ? '복사됨!' : 'EMR로 복사'}
            </button>
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
