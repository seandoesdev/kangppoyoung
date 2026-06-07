// 백엔드 호출 API 레이어 — 프론트엔드에서 서버를 호출하는 함수는 모두 여기에 모여 있다.
// 화면 컴포넌트는 data/mock.ts 가 아니라 이 모듈만 import 해서 서버와 통신한다.
//
// docs/api/openapi.yaml 이 계약의 단일 기준이며, 함수명은 각 엔드포인트의 operationId 와 일치한다.

export * from './types'
export { ApiError } from './client'

export {
  searchPolicy,
  listSearchHistory,
  listSearchExamples,
  addSearchExample,
  deleteSearchExample,
} from './search'

export {
  getNotice,
  getNoticeVersionDiff,
  registerNoticeRevision,
  preprocessNoticePdf,
} from './notices'

export { getRankings } from './rankings'
export { getOnboardingGuide } from './onboarding'
