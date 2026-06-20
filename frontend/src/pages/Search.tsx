import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { SEARCH_SCENARIOS } from '../data/mock'
import type { SearchResult } from '../api/types'
import { searchPolicy } from '../api/search'
import { ApiError } from '../api/client'
import { useSearchHistory } from '../context/SearchHistoryContext'
import {
  ArticleCard,
  Card,
  PageHeader,
  SectionLabel,
  SourceChip,
} from '../components/ui'

const MAX_EXAMPLES = 5

export default function Search() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const { getBySessionId, fetchSession, refresh } = useSearchHistory()

  const [query, setQuery] = useState('')
  const [result, setResult] = useState<SearchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 예시 질문 (사용자가 최대 5개까지 추가/삭제)
  const [examples, setExamples] = useState<string[]>(
    SEARCH_SCENARIOS.map((s) => s.query).slice(0, 3),
  )
  const [newExample, setNewExample] = useState('')

  // 검색 중복 실행 가드(연타 대비; loading state 의존 없이 안정 동작).
  const busyRef = useRef(false)

  // URL(/q/<sessionId>) 변경 시 그 세션을 복원한다. 적재된 목록에 있으면 즉시, 없으면(딥링크/새로고침)
  // 백엔드 단건 조회로 가져온다. sessionId 가 없으면(홈 '/') 새 대화로 초기화한다.
  useEffect(() => {
    if (!sessionId) {
      setResult(null)
      setQuery('')
      setError(null)
      return
    }
    const cached = getBySessionId(sessionId)
    if (cached) {
      setQuery(cached.query)
      setResult(cached)
      setError(null)
      return
    }
    let ignore = false
    setLoading(true)
    setError(null)
    fetchSession(sessionId)
      .then((item) => {
        if (ignore) return
        if (item?.result) {
          setQuery(item.query)
          setResult(item.result)
        } else {
          setResult(null)
          setQuery('')
          setError('해당 대화를 찾을 수 없습니다.')
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })
    return () => {
      ignore = true
    }
    // sessionId 변경에만 반응한다(getBySessionId/fetchSession 은 변경 시점의 최신 클로저 사용).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  // 새 검색: 백엔드 질의 → 기록 갱신 → 생성된 세션(/q/<sessionId>)으로 이동(딥링크·공유 가능).
  async function submit(q: string) {
    const trimmed = q.trim()
    if (!trimmed || busyRef.current) return
    busyRef.current = true
    setLoading(true)
    setError(null)
    setQuery(trimmed)
    try {
      const r = await searchPolicy(trimmed)
      setResult(r)
      const fresh = await refresh() // 사이드바 채팅 기록 갱신 + 신규 sessionId 획득
      const newest = fresh && fresh[0]
      if (newest?.sessionId) navigate(`/q/${encodeURIComponent(newest.sessionId)}`)
    } catch (e) {
      setResult(null)
      setError(e instanceof ApiError ? e.message : '검색 중 오류가 발생했습니다.')
    } finally {
      setLoading(false)
      busyRef.current = false
    }
  }

  function addExample() {
    const v = newExample.trim()
    if (!v || examples.length >= MAX_EXAMPLES || examples.includes(v)) return
    setExamples((prev) => [...prev, v])
    setNewExample('')
  }

  function removeExample(q: string) {
    setExamples((prev) => prev.filter((e) => e !== q))
  }

  return (
    <div>
      <PageHeader
        title="통합 검색"
        desc="규정·지침·절차나 민원 내용을 자연어로 질의하면 관련 문서·조항을 근거로 찾아드립니다. 전화 민원 응대 중에도 바로 검색해 근거 기반으로 답변하세요."
      />

      <Card className="mb-6">
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit(query)}
            placeholder="예: 서류 제출 기한이 어떻게 되나요?"
            autoFocus
            className="flex-1 rounded-lg border border-slate-300 px-4 py-2.5 text-sm outline-none focus:border-slate-900"
          />
          <button
            onClick={() => submit(query)}
            disabled={loading}
            className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {loading ? '검색 중…' : '검색'}
          </button>
        </div>

        {/* 예시 질문 — 최대 5개까지 추가 */}
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between">
            <SectionLabel>예시 질문</SectionLabel>
            <span className="text-xs text-slate-400">
              {examples.length} / {MAX_EXAMPLES}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {examples.map((q) => (
              <span
                key={q}
                className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white py-0.5 pl-2.5 pr-1 text-xs text-slate-600"
              >
                <button onClick={() => submit(q)} className="hover:text-slate-900">
                  {q}
                </button>
                <button
                  onClick={() => removeExample(q)}
                  className="flex h-4 w-4 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-rose-500"
                  aria-label="예시 질문 삭제"
                >
                  ×
                </button>
              </span>
            ))}

            {examples.length < MAX_EXAMPLES && (
              <span className="inline-flex items-center gap-1">
                <input
                  value={newExample}
                  onChange={(e) => setNewExample(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addExample()}
                  placeholder="예시 질문 추가"
                  className="w-40 rounded-full border border-dashed border-slate-300 px-2.5 py-0.5 text-xs outline-none focus:border-slate-900"
                />
                <button
                  onClick={addExample}
                  disabled={!newExample.trim()}
                  className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 disabled:opacity-40"
                >
                  + 추가
                </button>
              </span>
            )}
          </div>
        </div>
      </Card>

      {error && (
        <Card className="mb-6 border-l-4 border-l-rose-400">
          <p className="text-sm text-rose-600">{error}</p>
        </Card>
      )}

      {result && <ResultView result={result} />}
    </div>
  )
}

/**
 * 답변을 단계별로 줄바꿈한다. 명시적 줄바꿈이 있으면 그대로, 없으면 단계 표시
 * (원형숫자 ①~⑳, "1." "2)" 등) 앞에서 줄을 나눈다. 단계 구분 화살표(→)는 줄 끝에서 정리.
 */
function splitAnswer(text: string): string[] {
  let s = (text ?? '').trim()
  if (!s) return []
  if (!s.includes('\n')) {
    s = s
      .replace(/(?=[①-⑳])/g, '\n') // 원형숫자 단계 앞 줄바꿈
      .replace(/\s+(?=\d{1,2}[.)]\s)/g, '\n') // "1." "2)" 번호 항목 앞 줄바꿈
  }
  return s
    .split('\n')
    .map((line) => line.replace(/^[\s→·]+/, '').replace(/[\s→·]+$/, '').trim())
    .filter(Boolean)
}

function ResultView({ result }: { result: SearchResult }) {
  return (
    <div className="space-y-6">
      {/* 답변 */}
      <Card>
        <SectionLabel>답변</SectionLabel>
        <div className="space-y-1 text-sm leading-relaxed text-slate-800">
          {splitAnswer(result.answer).map((line, i) => (
            <p key={i}>{line}</p>
          ))}
        </div>
        {result.evidence.length > 0 && (
          <div className="mt-3">
            <SectionLabel>근거 조항</SectionLabel>
            <div className="space-y-2">
              {result.evidence.map((a, i) => (
                <ArticleCard key={i} article={a} />
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* 중복 절차: 요약 1건 + 출처 */}
      {result.duplicateSummary && (
        <Card className="border-l-4 border-l-emerald-400">
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-700">
              중복 절차 — 요약
            </span>
            <span className="text-xs text-slate-400">동일 내용은 하나로 요약</span>
          </div>
          <p className="mb-3 text-sm leading-relaxed text-slate-800">
            {result.duplicateSummary.summary}
          </p>
          <div className="flex flex-wrap gap-2">
            {result.duplicateSummary.sources.map((a, i) => (
              <SourceChip key={i} article={a} />
            ))}
          </div>
        </Card>
      )}

      {/* 상충 절차: 원문 그대로 병렬 + 출처 */}
      {result.conflicts && result.conflicts.length > 0 && (
        <Card className="border-l-4 border-l-rose-400">
          <div className="mb-3 flex items-center gap-2">
            <span className="rounded bg-rose-100 px-2 py-0.5 text-xs font-bold text-rose-700">
              상충 절차 — 원문 병렬
            </span>
            <span className="text-xs text-slate-400">임의 통합 없이 원문 그대로 표시</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {result.conflicts.map((a, i) => (
              <ArticleCard key={i} article={a} />
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
