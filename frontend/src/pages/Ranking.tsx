import { useEffect, useState } from 'react'
import { getRankings } from '../api/rankings'
import { RANKING_PERIODS } from '../api/periods'
import type { RankingItem } from '../api/types'
import { ApiError } from '../api/client'
import { Card, PageHeader, SectionLabel, SourceChip } from '../components/ui'

// 추세 아이콘 — 백엔드 trend 는 현재 'same' 고정(실 추세 산출은 후속). up/down 일 때만 노출한다.
const trendIcon: Record<'up' | 'down', string> = {
  up: '🔺',
  down: '🔻',
}

export default function Ranking() {
  const [period, setPeriod] = useState<string>(RANKING_PERIODS[0])
  const [items, setItems] = useState<RankingItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 기간 변경 시 재조회. 직전 요청 응답이 늦게 도착해 최신 결과를 덮어쓰지 않도록 ignore 가드.
  useEffect(() => {
    let ignore = false
    setLoading(true)
    setError(null)
    getRankings(period)
      .then((data) => {
        if (!ignore) setItems(data)
      })
      .catch((e) => {
        if (ignore) return
        setItems([])
        setError(e instanceof ApiError ? e.message : '랭킹을 불러오지 못했습니다.')
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })
    return () => {
      ignore = true
    }
  }, [period])

  const max = items.length ? Math.max(...items.map((i) => i.searchCount)) : 0

  return (
    <div>
      <PageHeader
        title="질문 분석"
        desc="저장된 질의·답변을 기간별로 카테고리화하고 빈도순 랭킹을 보여줍니다. 이 랭킹이 온보딩 가이드의 학습 우선순위로 활용됩니다."
      />

      <div className="mb-5 flex items-center gap-2">
        <SectionLabel>집계 기간</SectionLabel>
        <div className="flex gap-1">
          {RANKING_PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                period === p ? 'bg-slate-900 text-white' : 'border border-slate-200 text-slate-600'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <Card className="mb-5 border-l-4 border-l-rose-400">
          <p className="text-sm text-rose-600">{error}</p>
        </Card>
      )}

      {loading ? (
        <Card>
          <p className="text-sm text-slate-500">집계 중…</p>
        </Card>
      ) : error ? null : items.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-500">
            집계된 질문이 없습니다. 통합 검색 기록이 쌓이면 빈도순으로 표시됩니다.
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <Card key={item.rank}>
              <div className="flex items-start gap-4">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-900 text-sm font-bold text-white">
                  {item.rank}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-base font-bold text-slate-900">{item.category}</span>
                    {(item.trend === 'up' || item.trend === 'down') && (
                      <span className="text-xs">{trendIcon[item.trend]}</span>
                    )}
                  </div>
                  <p className="mt-0.5 text-sm text-slate-500">대표 질문: "{item.questionExample}"</p>

                  {/* 검색량 막대 */}
                  <div className="mt-2 flex items-center gap-2">
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-slate-800"
                        style={{ width: max > 0 ? `${(item.searchCount / max) * 100}%` : '0%' }}
                      />
                    </div>
                    <span className="w-20 text-right text-xs text-slate-500">
                      검색 {item.searchCount}회
                    </span>
                  </div>

                  <div className="mt-2 flex flex-wrap gap-2">
                    {item.relatedArticles.map((a, i) => (
                      <SourceChip key={i} article={a} />
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <p className="mt-5 rounded-lg bg-indigo-50 p-3 text-xs text-indigo-700">
        💡 위 랭킹(많이 검색한 순)이 그대로 신규입사자 학습 우선순위로 환산됩니다. → 온보딩
        가이드에서 확인하세요.
      </p>
    </div>
  )
}
