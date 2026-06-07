// 신규입사자 학습 우선순위 안내 (OpenAPI tag: onboarding)
import { http } from './client'
import type { OnboardingItem } from './types'

/** GET /onboarding — 실무 검색·조회 빈도 기반으로 학습해야 할 항목을 우선순위 순으로 안내 */
export function getOnboardingGuide(period = '최근 30일'): Promise<OnboardingItem[]> {
  return http.get<OnboardingItem[]>('/onboarding', { period })
}
