import { useState, useEffect, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import {
  getOnePager,
  rerunOnePagerReview,
  submitDoctorResponse
} from '../../services/api.js'
import DoctorOnePager from './DoctorOnePager.jsx'
import DoctorAgendaPanel from './DoctorAgendaPanel.jsx'
import './DoctorView.css'

// 의사용 원페이퍼 화면의 컨테이너입니다.
// 좌측 원페이퍼 요약과 우측 환자 질문/답변 패널을 같은 sessionId로 묶어 보여줍니다.

// UI 개선안 2 적용
// ────────────────────────────────────────
// 좌측 (visit_type 분기):
//   - 카드 1: 증상 / 변화 추적 카드 (초진/재진별 다른 형태)
//   - 카드 2: 의료진 확인 항목 (초진/재진별 추가 항목)
//   - 카드 3: 기록용 문장 (EMR 복사)
//
// 우측 (visit_type 무관 공통):
//   - 환자 질문 + 답변 입력 인라인 (agenda + textarea per question)
//   - 환자 발화 원문 카드 상시 표시 (Q4 누락 방지 4중 묘수 ④)
//
// 상단 가로 띠 (전체 폭):
//   - 위험 플래그 amber 배지 (실제 safety flag)
//   - 환자 정보 (이름·나이·진료과·visit_type)

export default function DoctorView() {
  const { sessionId } = useParams()
  const [sessionData, setSessionData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitStatus, setSubmitStatus] = useState(null)
  const [onepagerStatus, setOnepagerStatus] = useState(null)

  // 화면 진입 시 백엔드에 저장된 최신 onepager JSON을 조회합니다.
  useEffect(() => {
    let alive = true
    setLoading(true)
    getOnePager(sessionId).then(data => {
      if (!alive) return
      setSessionData(data)
    }).finally(() => {
      if (alive) setLoading(false)
    })
    return () => {
      alive = false
    }
  }, [sessionId])

  const refreshOnePager = async () => {
    if (!sessionId) return
    setOnepagerStatus('refreshing')
    try {
      const data = await getOnePager(sessionId)
      setSessionData(data)
      setOnepagerStatus('refreshed')
      setTimeout(() => setOnepagerStatus(null), 1600)
    } catch (err) {
      console.error('원페이퍼 새로고침 실패:', err)
      setOnepagerStatus('error')
    }
  }

  const handleAiReview = async () => {
    if (!sessionId) return
    setOnepagerStatus('reviewing')
    try {
      const data = await rerunOnePagerReview(sessionId)
      setSessionData(data)
      setOnepagerStatus('reviewed')
      setTimeout(() => setOnepagerStatus(null), 1800)
    } catch (err) {
      console.error('원페이퍼 AI 재검토 실패:', err)
      setOnepagerStatus('error')
    }
  }

  // 의사가 작성한 답변과 강조사항을 저장하고 환자 안내문 생성 결과 상태를 표시합니다.
  const handleSubmitResponse = async ({ answers, additionalNotes }) => {
    if (!sessionId) {
      setSubmitStatus('error')
      return
    }
    setSubmitStatus('submitting')
    try {
      const result = await submitDoctorResponse({
        sessionId,
        reviewerId: 'doctor-web',
        answers,
        additionalNotes
      })
      if (result.guide_generation_valid !== false) {
        setSubmitStatus('success')
      } else {
        setSubmitStatus('invalid')
      }
    } catch (err) {
      console.error('의사 답변 전송 실패:', err)
      setSubmitStatus('error')
    }
  }

  if (loading) {
    return <div className="doctor-loading">원페이퍼를 불러오는 중...</div>
  }

  return (
    <div className="doctor-view-v3">
      <DoctorOnePager
        sessionId={sessionId}
        sessionData={sessionData}
        onRefresh={refreshOnePager}
        onAiReview={handleAiReview}
        onepagerStatus={onepagerStatus}
        // Agenda + 답변 입력은 별도 우측 패널로 분리
        renderAgenda={false}
        // 우측 영역에 답변 입력 함께 표시
        sidePanel={
          <DoctorAgendaPanel
            sessionData={sessionData}
            submitStatus={submitStatus}
            onSubmit={handleSubmitResponse}
          />
        }
      />
    </div>
  )
}
