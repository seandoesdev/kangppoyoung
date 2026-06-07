// 자연어 검색 · 민원 응대 (OpenAPI tag: search)
import { http } from './client'
import type { SearchExample, SearchHistoryItem, SearchResult } from './types'

/** POST /search — 자연어로 규정·지침·절차를 질의하고 근거 조항이 포함된 답변 수신 */
export function searchPolicy(query: string): Promise<SearchResult> {
  return http.post<SearchResult>('/search', { query })
}

/** GET /search/history — 이전 질의·답변 이력을 최신순으로 조회 */
export function listSearchHistory(params?: {
  page?: number
  size?: number
}): Promise<SearchHistoryItem[]> {
  return http.get<SearchHistoryItem[]>('/search/history', params)
}

/** GET /search/examples — 자주 쓰는 예시 질문 목록 조회 (최대 5개) */
export function listSearchExamples(): Promise<SearchExample[]> {
  return http.get<SearchExample[]>('/search/examples')
}

/** POST /search/examples — 자주 쓰는 예시 질문 추가 (최대 5개) */
export function addSearchExample(text: string): Promise<SearchExample> {
  return http.post<SearchExample>('/search/examples', { text })
}

/** DELETE /search/examples/{exampleId} — 등록된 예시 질문 삭제 */
export function deleteSearchExample(exampleId: string): Promise<void> {
  return http.delete(`/search/examples/${encodeURIComponent(exampleId)}`)
}
