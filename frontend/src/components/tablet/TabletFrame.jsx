// 세로 태블릿 외곽 프레임 (검은 베젤 + 상단 스피커 + 하단 홈 표시)
// children은 .tablet-screen 내부에 들어감

// 태블릿 문진 화면을 감싸는 공통 프레임입니다.
// 실제 태블릿 접속 화면(device)과 개발 미리보기(preview)의 폭/여백 차이를 여기서 나눕니다.
export default function TabletFrame({ children, visitType, variant = 'preview' }) {
  // visitType에 따라 'initial' 또는 'followup' CSS 클래스로 색상 테마 적용
  const themeClass = visitType ? visitType : 'initial'

  if (variant === 'device') {
    return (
      <div className="tablet-live-shell">
        <div className={`tablet-screen tablet-screen-device ${themeClass}`}>
          {children}
        </div>
      </div>
    )
  }

  return (
    <div className="tablet-frame">
      <div className={`tablet-screen ${themeClass}`}>
        {children}
      </div>
    </div>
  )
}
