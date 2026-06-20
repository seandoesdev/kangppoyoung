import { useEffect, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useSearchHistory } from '../context/SearchHistoryContext'

const linkClass = (isActive: boolean) =>
  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
    isActive ? 'bg-slate-900 font-semibold text-white' : 'text-slate-600 hover:bg-slate-100'
  }`

export default function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const noticeOpen = location.pathname.startsWith('/notice')
  const [open, setOpen] = useState(noticeOpen)
  const [historyOpen, setHistoryOpen] = useState(true)

  const { items, loading, hasMore, loadMore, remove, clear } = useSearchHistory()
  // 현재 보고 있는 세션(/q/<sessionId>)을 강조 표시한다.
  const sessionMatch = location.pathname.match(/^\/q\/(.+)$/)
  const activeSession = sessionMatch ? decodeURIComponent(sessionMatch[1]) : null

  const scrollRef = useRef<HTMLDivElement | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  // 무한 스크롤: 스크롤 컨테이너 하단 sentinel 이 보이면 다음 페이지 적재.
  // items 변동 시 재구독해 (컨테이너보다 짧은 목록에서) 재발화 누락을 보완한다.
  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel || !historyOpen) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) loadMore()
      },
      { root: scrollRef.current ?? null },
    )
    io.observe(sentinel)
    return () => io.disconnect()
  }, [historyOpen, loadMore, items.length, hasMore])

  async function handleRemove(sessionId: string) {
    try {
      await remove(sessionId)
    } catch {
      // 삭제 실패 시 항목 유지
    }
  }

  async function handleClear() {
    if (!window.confirm('채팅 기록을 모두 지울까요? (모든 사용자 공용)')) return
    try {
      await clear()
    } catch {
      // 무시
    }
  }

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-5 py-5">
        <div className="text-base font-bold leading-tight text-slate-900">정책자금 지원</div>
        <div className="text-sm text-slate-500">업무 플랫폼</div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        <NavLink to="/" end className={({ isActive }) => linkClass(isActive)}>
          <span className="text-base">🔍</span>
          <span className="flex-1">통합 검색</span>
        </NavLink>

        {/* 정책 자금 공고 — 소메뉴 그룹 */}
        <div>
          <button
            onClick={() => setOpen((v) => !v)}
            className={linkClass(noticeOpen) + ' w-full'}
          >
            <span className="text-base">📋</span>
            <span className="flex-1 text-left">정책 자금 공고</span>
            <span className={`text-xs transition-transform ${open ? 'rotate-90' : ''}`}>›</span>
          </button>
          {open && (
            <div className="mt-1 space-y-1 pl-7">
              <NavLink
                to="/notice/regulation"
                className={({ isActive }) =>
                  `block rounded-lg px-3 py-2 text-sm transition ${
                    isActive ? 'bg-slate-100 font-semibold text-slate-900' : 'text-slate-500 hover:bg-slate-100'
                  }`
                }
              >
                공고
              </NavLink>
              <NavLink
                to="/notice/reference"
                className={({ isActive }) =>
                  `block rounded-lg px-3 py-2 text-sm transition ${
                    isActive ? 'bg-slate-100 font-semibold text-slate-900' : 'text-slate-500 hover:bg-slate-100'
                  }`
                }
              >
                참고자료
              </NavLink>
            </div>
          )}
        </div>

        <NavLink to="/ranking" className={({ isActive }) => linkClass(isActive)}>
          <span className="text-base">📊</span>
          <span className="flex-1">질문 분석</span>
        </NavLink>

        <NavLink to="/onboarding" className={({ isActive }) => linkClass(isActive)}>
          <span className="text-base">🎓</span>
          <span className="flex-1">온보딩 가이드</span>
        </NavLink>

        {/* 채팅 기록 — 무한 스크롤 + 항목/전체 삭제. 클릭 시 /q/<sessionId> 로 복원 */}
        <div>
          <button
            onClick={() => setHistoryOpen((v) => !v)}
            className={linkClass(false) + ' w-full'}
          >
            <span className="text-base">💬</span>
            <span className="flex-1 text-left">채팅 기록</span>
            <span className={`text-xs transition-transform ${historyOpen ? 'rotate-90' : ''}`}>›</span>
          </button>
          {historyOpen && (
            <div className="mt-1">
              <div ref={scrollRef} className="max-h-64 space-y-1 overflow-y-auto pl-7 pr-1">
                {items.length === 0 && !loading && (
                  <p className="px-3 py-2 text-xs text-slate-400">채팅 기록 없음</p>
                )}
                {items.map((it) => {
                  const active = activeSession === it.sessionId
                  return (
                    <div
                      key={it.sessionId}
                      className={`group flex items-center gap-1 rounded-lg pr-1 transition ${
                        active ? 'bg-slate-100' : 'hover:bg-slate-100'
                      }`}
                    >
                      <button
                        onClick={() => navigate(`/q/${encodeURIComponent(it.sessionId)}`)}
                        title={it.query}
                        className={`min-w-0 flex-1 truncate px-3 py-2 text-left text-sm transition ${
                          active ? 'font-semibold text-slate-900' : 'text-slate-500'
                        }`}
                      >
                        {it.query}
                      </button>
                      <button
                        onClick={() => handleRemove(it.sessionId)}
                        aria-label="기록 삭제"
                        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-slate-300 opacity-0 transition hover:bg-slate-200 hover:text-rose-500 group-hover:opacity-100"
                      >
                        ×
                      </button>
                    </div>
                  )
                })}
                {hasMore && <div ref={sentinelRef} className="h-4" />}
                {loading && (
                  <p className="px-3 py-2 text-xs text-slate-400">불러오는 중…</p>
                )}
              </div>
              {items.length > 0 && (
                <button
                  onClick={handleClear}
                  className="mt-1 w-full px-3 py-1.5 text-left text-xs text-slate-400 transition hover:text-rose-500"
                >
                  전체 지우기
                </button>
              )}
            </div>
          )}
        </div>
      </nav>

      <div className="border-t border-slate-100 p-4 text-xs text-slate-400">
        © 2026 정책자금 지원팀
      </div>
    </aside>
  )
}
