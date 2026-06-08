// 프론트엔드 전체에서 쓰는 API 공개 진입점입니다.
// 화면 컴포넌트는 내부 파일 구조를 몰라도 여기서 필요한 함수만 가져다 쓰면 됩니다.
export {
  isRemoteApiEnabled,
} from './api/client.js'

export {
  createIntakeSession,
  getDoctorQueue,
  getIntakeSession,
  recordPatientConsent,
  requestStaffHelp,
} from './api/sessions.js'

export {
  processTranscript,
} from './api/transcripts.js'

export {
  getOnePager,
  rerunOnePagerReview,
  submitDoctorResponse,
  getPatientGuide,
} from './api/doctor.js'
