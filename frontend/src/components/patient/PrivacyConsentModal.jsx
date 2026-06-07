import { useState } from 'react'

export const PRIVACY_CONSENT_VERSION = 'munjin-privacy-consent-2026-06-07'

export const PRIVACY_NOTICE_ITEMS = [
  '환자 확인 및 문진 세션 생성',
  '음성 문진의 실시간 텍스트 변환',
  '의료진 확인용 원페이퍼 및 환자 안내문 생성',
  '문진 중 위험 표현 감지와 직원 호출 처리',
]

export const SENSITIVE_NOTICE_ITEMS = [
  '증상, 경과, 복약, 병력 등 건강 관련 문진 답변',
  '환자가 의사에게 묻고 싶은 질문과 진료 후 안내 내용',
]

export const RETENTION_NOTICE = 'MVP 시연 및 검증 목적의 세션 데이터는 최대 3일 보관 후 삭제하는 정책을 적용합니다.'

// 환자가 문진을 시작하기 전 개인정보와 건강정보 처리 범위를 확인하는 차단형 팝업입니다.
// 법률 자문 문구가 아니라 MVP 심사/시연에서 필요한 최소 고지 항목을 명확히 보여주는 용도입니다.
export default function PrivacyConsentModal({
  patientName = '환자',
  isSaving = false,
  error = '',
  rejected = false,
  onAccept,
  onReject,
  onStaffHelp,
}) {
  const [privacyChecked, setPrivacyChecked] = useState(false)
  const [sensitiveChecked, setSensitiveChecked] = useState(false)
  const canAccept = privacyChecked && sensitiveChecked && !isSaving

  return (
    <div className="privacy-consent-backdrop" role="dialog" aria-modal="true" aria-labelledby="privacy-consent-title">
      <section className="privacy-consent-modal">
        <div className="privacy-consent-kicker">문진 시작 전 확인</div>
        <h2 id="privacy-consent-title">개인정보 수집·이용 및 건강정보 처리 동의</h2>
        <p className="privacy-consent-lead">
          {patientName}님의 음성 문진은 의료진 확인을 돕기 위한 참고자료로만 사용됩니다.
          동의하지 않으셔도 직원에게 말씀하시면 수기 문진으로 도와드릴 수 있습니다.
        </p>

        <div className="privacy-consent-section">
          <h3>수집·이용 목적</h3>
          <ul>
            {PRIVACY_NOTICE_ITEMS.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>

        <div className="privacy-consent-grid">
          <div className="privacy-consent-section">
            <h3>수집 항목</h3>
            <p>
              이름 또는 표시명, 생년월일/연령, 성별, 접수번호, 진료과, 문진 답변 텍스트,
              실시간 전사 결과, 의료진 답변 및 안내문 내용
            </p>
          </div>
          <div className="privacy-consent-section">
            <h3>보유 및 삭제</h3>
            <p>{RETENTION_NOTICE}</p>
            <p>음성 원본 파일은 저장하지 않고, 문진에 필요한 텍스트만 세션에 기록합니다.</p>
          </div>
        </div>

        <div className="privacy-consent-section privacy-consent-warning">
          <h3>민감정보 처리 항목</h3>
          <p>
            문진 답변에는 증상, 복약, 병력 등 건강에 관한 정보가 포함될 수 있습니다.
            해당 정보는 의료진이 확인할 원페이퍼와 환자 안내문 생성을 위해서만 처리합니다.
          </p>
        </div>

        <label className="privacy-consent-check">
          <input
            type="checkbox"
            checked={privacyChecked}
            onChange={(event) => setPrivacyChecked(event.target.checked)}
          />
          <span>개인정보 수집·이용 목적, 항목, 보유 기간, 동의 거부 권리를 확인했고 이에 동의합니다.</span>
        </label>
        <label className="privacy-consent-check">
          <input
            type="checkbox"
            checked={sensitiveChecked}
            onChange={(event) => setSensitiveChecked(event.target.checked)}
          />
          <span>증상·복약·병력 등 건강정보가 포함될 수 있음을 확인했고 민감정보 처리에 동의합니다.</span>
        </label>

        {error && <p className="privacy-consent-error">{error}</p>}
        {rejected && (
          <p className="privacy-consent-rejected">
            동의하지 않으신 경우 음성 문진은 진행하지 않습니다. 접수 직원에게 수기 문진을 요청해 주세요.
          </p>
        )}

        <div className="privacy-consent-actions">
          <button type="button" className="privacy-consent-secondary" onClick={onReject} disabled={isSaving}>
            동의하지 않음
          </button>
          <button type="button" className="privacy-consent-help" onClick={onStaffHelp} disabled={isSaving}>
            직원 도움 요청
          </button>
          <button type="button" className="privacy-consent-primary" onClick={onAccept} disabled={!canAccept}>
            {isSaving ? '저장 중...' : '동의하고 문진 시작'}
          </button>
        </div>
      </section>
    </div>
  )
}
