// 자주 묻는 질문 분석 · 랭킹 (OpenAPI tag: rankings)
import { http } from './client'
import type { RankingItem } from './types'

/** GET /rankings — 기간별로 자주 묻는 질문을 카테고리화하고 빈도순 랭킹으로 조회 */
export function getRankings(period: string): Promise<RankingItem[]> {
  return http.get<RankingItem[]>('/rankings', { period })
}
