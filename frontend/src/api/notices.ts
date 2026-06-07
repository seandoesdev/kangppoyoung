// 정책 자금 공고 · 문서 버전 관리 (OpenAPI tag: notices)
import { http } from './client'
import type {
  ContentBlock,
  DiffBlock,
  NoticeCategory,
  NoticeCategoryKey,
  NoticeRevisionRequest,
  NoticeVersion,
} from './types'

/** GET /notices/{category} — 공고 또는 참고자료 문서와 버전 목록 조회 */
export function getNotice(category: NoticeCategoryKey): Promise<NoticeCategory> {
  return http.get<NoticeCategory>(`/notices/${category}`)
}

/** GET /notices/{category}/versions/{version}/diff — 지정 버전과 바로 전 버전의 블록 단위 변경 내역 조회 */
export function getNoticeVersionDiff(
  category: NoticeCategoryKey,
  version: string,
): Promise<DiffBlock[]> {
  return http.get<DiffBlock[]>(
    `/notices/${category}/versions/${encodeURIComponent(version)}/diff`,
  )
}

/** POST /notices/{category}/revisions — 검토·승인 완료된 개정본을 새 버전으로 확정 등록 */
export function registerNoticeRevision(
  category: NoticeCategoryKey,
  revision: NoticeRevisionRequest,
): Promise<NoticeVersion> {
  return http.post<NoticeVersion>(`/notices/${category}/revisions`, revision)
}

/** POST /notices/{category}/revisions/preprocess — 개정 PDF 업로드 → 텍스트·표·도표 자동 추출(검토용 블록) */
export function preprocessNoticePdf(
  category: NoticeCategoryKey,
  file: File,
): Promise<{ blocks: ContentBlock[] }> {
  const form = new FormData()
  form.append('file', file)
  return http.postForm<{ blocks: ContentBlock[] }>(
    `/notices/${category}/revisions/preprocess`,
    form,
  )
}
