import { useEffect, useRef, useState } from 'react'
import { loginWithAccessCode, setAuthPromptHandler } from '../../services/api/client.js'
import './RoleLoginModal.css'

const ROLE_LABEL = {
  staff: '직원',
  doctor: '의료진',
}

const ROLE_TITLE = {
  staff: '직원 접속 확인',
  doctor: '의료진 접속 확인',
}

// API 클라이언트가 내부 화면 접근 권한을 요구할 때 표시되는 로그인 모달입니다.
// 브라우저 기본 prompt 대신 앱 디자인 안에서 접근 코드를 받고,
// 성공하면 백엔드가 발급한 짧은 시간 유효 세션 토큰을 API 클라이언트에 돌려줍니다.
export default function RoleLoginModal() {
  const [request, setRequest] = useState(null)
  const [accessCode, setAccessCode] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    setAuthPromptHandler(({ role }) => new Promise((resolve, reject) => {
      setRequest({ role, resolve, reject })
      setAccessCode('')
      setError('')
      setSubmitting(false)
    }))

    return () => setAuthPromptHandler(null)
  }, [])

  useEffect(() => {
    if (!request) return
    const timer = window.setTimeout(() => inputRef.current?.focus(), 50)
    return () => window.clearTimeout(timer)
  }, [request])

  if (!request) return null

  const role = request.role
  const label = ROLE_LABEL[role] || '사용자'

  const submit = async (event) => {
    event.preventDefault()
    const value = accessCode.trim()
    if (!value) {
      setError('접근 코드를 입력해 주세요.')
      return
    }

    setSubmitting(true)
    setError('')
    try {
      const session = await loginWithAccessCode(role, value)
      request.resolve(session)
      setRequest(null)
    } catch (loginError) {
      setError(loginError.message || '접근 코드가 맞지 않습니다.')
      setSubmitting(false)
    }
  }

  return (
    <div className="role-login-backdrop" role="presentation">
      <form className="role-login-modal" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="role-login-title">
        <div className="role-login-kicker">문진톡톡</div>
        <h2 id="role-login-title">{ROLE_TITLE[role] || '접속 확인'}</h2>
        <p>
          {label} 화면은 개인정보와 문진 결과를 다루는 보호 화면입니다.
          <br />
          접수처에서 안내받은 접근 코드를 입력해 주세요.
        </p>

        <label className="role-login-field">
          <span>{label} 접근 코드</span>
          <input
            ref={inputRef}
            type="password"
            inputMode="text"
            autoComplete="off"
            value={accessCode}
            onChange={(event) => setAccessCode(event.target.value)}
            placeholder="접근 코드 입력"
          />
        </label>

        {error ? <div className="role-login-error">{error}</div> : null}

        <div className="role-login-actions">
          <button type="submit" className="role-login-primary" disabled={submitting}>
            {submitting ? '확인 중' : '로그인'}
          </button>
        </div>
      </form>
    </div>
  )
}
