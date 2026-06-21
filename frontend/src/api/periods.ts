// 질문 분석(UC-4)·온보딩(UC-5)의 집계 기간 선택지.
// 백엔드 RankingService.days() 가 기간 문자열에 "7" 포함 여부로 7일/30일을 판정하므로 표기를 그대로 유지한다.
// (화면이 실 API 로 전환되며 mock 의 RANKING_PERIODS 를 이곳으로 이전.)
export const RANKING_PERIODS = ['최근 7일', '최근 30일'] as const
