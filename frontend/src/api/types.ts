// 백엔드 API 계약(DTO) 타입 — docs/api/openapi.yaml 의 components/schemas 와 1:1 대응.
// 백엔드 응답/요청의 단일 기준이며, 화면 컴포넌트는 이 타입을 통해서만 서버 데이터를 다룬다.

export type DocType = '규정' | '지침' | '절차'

/** PolicyDocument */
export interface PolicyDocument {
  id: string
  title: string
  type: DocType
  updatedAt: string
  /** 개정 시 이 문서 하나만 갱신하는 단일 진실 문서 여부 */
  isSingleSource: boolean
}

/** Article — 답변·랭킹의 근거가 되는 조항 단위 */
export interface Article {
  docId: string
  docTitle: string
  docType: DocType
  articleNo: string
  text: string
}

/** SearchRequest */
export interface SearchRequest {
  query: string
}

/** SearchResult — 자연어 질의에 대한 검색 응답 */
export interface SearchResult {
  query: string
  answer: string
  /** 답변의 직접 근거 조항 */
  evidence: Article[]
  /** 중복 절차를 하나로 요약 + 출처 */
  duplicateSummary?: {
    summary: string
    sources: Article[]
  }
  /** 상충 절차 — 원문 그대로 병렬 표시 + 출처 */
  conflicts?: Article[]
}

/** SearchHistoryItem */
export interface SearchHistoryItem {
  id: string
  /** URL(/q/{sessionId})로 이 기록을 식별·복원하는 UUID v4 */
  sessionId: string
  query: string
  createdAt: string
  result?: SearchResult
}

/** SearchExample */
export interface SearchExample {
  id: string
  text: string
}

/** ContentBlock (text | image, discriminator: type) */
export type ContentBlock =
  | { type: 'text'; text: string }
  | { type: 'image'; src: string; name?: string }

/** NoticeVersion */
export interface NoticeVersion {
  version: string
  date: string
  blocks: ContentBlock[]
}

/** NoticeCategory */
export interface NoticeCategory {
  key: 'regulation' | 'reference'
  label: string
  docTitle: string
  /** 날짜 내림차순(최신 먼저) */
  versions: NoticeVersion[]
}

export type NoticeCategoryKey = NoticeCategory['key']

/** NoticeRevisionRequest — 검토·승인 완료된 갱신본 */
export interface NoticeRevisionRequest {
  /** 시행일 (YYYY-MM-DD) */
  effectiveDate: string
  blocks: ContentBlock[]
}

/** DiffBlock */
export interface DiffBlock {
  type: 'same' | 'add' | 'del'
  block: ContentBlock
}

export type Trend = 'up' | 'down' | 'same'

/** RankingItem */
export interface RankingItem {
  rank: number
  category: string
  questionExample: string
  searchCount: number
  viewCount: number
  trend: Trend
  /** 이 카테고리의 핵심 근거 문서/조항 */
  relatedArticles: Article[]
}

/** OnboardingItem — 실무 검색·조회 빈도를 학습 우선순위로 환산한 항목 */
export interface OnboardingItem {
  /** 학습 순서(검색·조회 빈도 높은 순) */
  order: number
  category: string
  /** 선정 근거 설명(왜 먼저 봐야 하는지) */
  reason: string
  searchCount: number
  viewCount: number
  relatedArticles: Article[]
}

/** Error */
export interface ApiErrorBody {
  code: string
  message: string
}
