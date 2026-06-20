// 채팅(검색) 기록 공유 상태. 백엔드 GET /search/history 를 단일 진실 출처로 두고,
// 항상 마운트되는 Sidebar 와 라우트별 마운트되는 Search 가 동일 인스턴스를 구독한다.
// 각 기록은 UUID sessionId 로 식별되며 URL(/q/<sessionId>) 로 복원·공유된다.
//
// 동시성: reset(refresh/초기적재)과 append(loadMore), clear 가 겹칠 수 있으므로 세대(gen) 토큰으로
// 직렬화한다. reset/clear 는 gen 을 올려 진행 중 append 응답을 폐기시키고, append 는 자신의 gen 이
// 아직 최신일 때만 결과를 반영한다.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { SearchHistoryItem, SearchResult } from '../api/types'
import {
  clearSearchHistory,
  deleteSearchHistory,
  getSearchHistoryItem,
  listSearchHistory,
} from '../api/search'

const PAGE_SIZE = 20

interface SearchHistoryValue {
  items: SearchHistoryItem[]
  loading: boolean
  error: string | null
  /** 다음 페이지가 더 있는지 (마지막 응답이 PAGE_SIZE 만큼 찼으면 true) */
  hasMore: boolean
  /** 다음 페이지를 이어 적재 (무한 스크롤). */
  loadMore: () => void
  /** 0페이지부터 다시 적재 후 최신 목록을 반환 (새 검색 직후 최신 반영·신규 sessionId 획득). */
  refresh: () => Promise<SearchHistoryItem[] | undefined>
  /** sessionId 로 기록 1건 삭제 후 목록에서 낙관적 제거. */
  remove: (sessionId: string) => Promise<void>
  /** 기록 전체 삭제. */
  clear: () => Promise<void>
  /** 이미 적재된 목록에서 sessionId 의 답변 조회 (사이드바 클릭 즉시 복원용). */
  getBySessionId: (sessionId: string) => SearchResult | undefined
  /** 목록에 없는 sessionId 를 백엔드에서 단건 조회 (딥링크/새로고침 복원용). 없으면 null. */
  fetchSession: (sessionId: string) => Promise<SearchHistoryItem | null>
}

const Ctx = createContext<SearchHistoryValue | null>(null)

export function SearchHistoryProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<SearchHistoryItem[]>([])
  const [page, setPage] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // append 중복 가드.
  const loadingRef = useRef(false)
  // 세대 토큰. reset/clear 시 증가시켜 진행 중인 stale 응답을 폐기한다.
  const genRef = useRef(0)

  const fetchPage = useCallback(
    async (nextPage: number, reset: boolean): Promise<SearchHistoryItem[] | undefined> => {
      // append 는 이미 로딩 중이면 건너뛴다. reset 은 진행 중 append 를 무효화하고 진행한다.
      if (!reset && loadingRef.current) return
      const gen = reset ? ++genRef.current : genRef.current
      loadingRef.current = true
      setLoading(true)
      setError(null)
      try {
        const batch = await listSearchHistory({ page: nextPage, size: PAGE_SIZE })
        if (gen !== genRef.current) return // 더 최신 reset/clear 발생 → 폐기
        setItems((prev) => (reset ? batch : [...prev, ...batch]))
        setPage(nextPage)
        setHasMore(batch.length === PAGE_SIZE)
        return batch
      } catch (e) {
        if (gen !== genRef.current) return
        setError(e instanceof Error ? e.message : '채팅 기록을 불러오지 못했습니다.')
        setHasMore(false)
        return
      } finally {
        if (gen === genRef.current) {
          loadingRef.current = false
          setLoading(false)
        }
      }
    },
    [],
  )

  // 최초 1회 적재.
  useEffect(() => {
    void fetchPage(0, true)
  }, [fetchPage])

  const loadMore = useCallback(() => {
    if (loadingRef.current || !hasMore) return
    void fetchPage(page + 1, false)
  }, [fetchPage, hasMore, page])

  const refresh = useCallback(() => fetchPage(0, true), [fetchPage])

  const remove = useCallback(async (sessionId: string) => {
    await deleteSearchHistory(sessionId)
    setItems((prev) => prev.filter((it) => it.sessionId !== sessionId))
  }, [])

  const clear = useCallback(async () => {
    await clearSearchHistory()
    genRef.current += 1 // 진행 중 적재 응답 무효화(비운 목록 부활 방지)
    loadingRef.current = false
    setItems([])
    setPage(0)
    setHasMore(false)
  }, [])

  const getBySessionId = useCallback(
    (sessionId: string) => items.find((it) => it.sessionId === sessionId)?.result,
    [items],
  )

  const fetchSession = useCallback(
    (sessionId: string) => getSearchHistoryItem(sessionId).catch(() => null),
    [],
  )

  return (
    <Ctx.Provider
      value={{
        items,
        loading,
        error,
        hasMore,
        loadMore,
        refresh,
        remove,
        clear,
        getBySessionId,
        fetchSession,
      }}
    >
      {children}
    </Ctx.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSearchHistory(): SearchHistoryValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useSearchHistory must be used within SearchHistoryProvider')
  return v
}
