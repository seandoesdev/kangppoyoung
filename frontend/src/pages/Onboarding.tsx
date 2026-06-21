import { useEffect, useState } from 'react'
import { getOnboardingGuide } from '../api/onboarding'
import { RANKING_PERIODS } from '../api/periods'
import type { OnboardingItem } from '../api/types'
import { ApiError } from '../api/client'
import { Card, PageHeader, SectionLabel } from '../components/ui'

// UC-5: 신규입사자 온보딩.
// 핵심 — 별도 추천 로직이 아니라 UC-4 랭킹(실무자가 많이 검색한 순)을 그대로 학습 우선순위로 환산한다.
// 백엔드(getOnboardingGuide)가 rank→order 환산과 선정 근거(reason)를 만들어 내려준다.

const DONE_STORAGE_KEY = 'onboarding:done'

function loadDone(): Record<number, boolean> {
  try {
    const raw = localStorage.getItem(DONE_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Record<number, boolean>) : {}
  } catch {
    return {}
  }
}

export default function Onboarding() {
  const [period, setPeriod] = useState<string>(RANKING_PERIODS[0])
  const [items, setItems] = useState<OnboardingItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 학습 진행 상태는 클라이언트 전용 — order 키로 localStorage 에 영속해 새로고침 후에도 유지한다.
  const [done, setDone] = useState<Record<number, boolean>>(loadDone)

  // 기간 변경 시 재조회. 늦게 도착한 직전 응답이 최신을 덮어쓰지 않도록 ignore 가드.
  useEffect(() => {
    let ignore = false
    setLoading(true)
    setError(null)
    getOnboardingGuide(period)
      .then((data) => {
        if (!ignore) setItems(data)
      })
      .catch((e) => {
        if (ignore) return
        setItems([])
        setError(e instanceof ApiError ? e.message : '학습 가이드를 불러오지 못했습니다.')
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })
    return () => {
      ignore = true
    }
  }, [period])

  useEffect(() => {
    try {
      localStorage.setItem(DONE_STORAGE_KEY, JSON.stringify(done))
    } catch {
      // localStorage 사용 불가 환경은 무시(진행률만 휘발).
    }
  }, [done])

  const total = items.length
  const doneCount = items.filter((c) => done[c.order]).length
  const pct = total ? (doneCount / total) * 100 : 0

  return (
    <div>
      <PageHeader
        title="온보딩 가이드"
        desc="실무자들이 많이 검색한 결과를 학습 우선순위로 환산해 '무엇부터 봐야 하는지'를 안내합니다."
      />

      {/* 데이터 출처 안내 — 임의 추천이 아님을 명시 + 기간 토글 */}
      <Card className="mb-5 border-l-4 border-l-indigo-400">
        <div className="flex items-center justify-between">
          <div>
            <SectionLabel>학습 우선순위 산출 근거</SectionLabel>
            <p className="text-sm text-slate-700">
              아래 순서는 <b>실무자들의 질문 분석 데이터</b>에서 자동 도출되었습니다. 임의 추천이
              아니라 <b>실제 검색 데이터</b> 기반입니다.
            </p>
          </div>
          <div className="flex gap-1">
            {RANKING_PERIODS.map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                  period === p
                    ? 'bg-slate-900 text-white'
                    : 'border border-slate-200 text-slate-600'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {error && (
        <Card className="mb-5 border-l-4 border-l-rose-400">
          <p className="text-sm text-rose-600">{error}</p>
        </Card>
      )}

      {loading ? (
        <Card>
          <p className="text-sm text-slate-500">학습 우선순위를 불러오는 중…</p>
        </Card>
      ) : error ? null : total === 0 ? (
        <Card>
          <p className="text-sm text-slate-500">
            학습 우선순위를 만들 데이터가 아직 없습니다. 통합 검색 기록이 쌓이면 자동으로 커리큘럼이
            생성됩니다.
          </p>
        </Card>
      ) : (
        <>
          {/* 진행률 */}
          <Card className="mb-5">
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="font-semibold text-slate-800">학습 진행률</span>
              <span className="text-slate-500">
                {doneCount} / {total} 완료
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          </Card>

          {/* 커리큘럼 = 랭킹 순서(백엔드가 order 오름차순으로 내려줌) */}
          <div className="space-y-3">
            {items.map((item, idx) => (
              <Card key={item.order} className={done[item.order] ? 'opacity-60' : ''}>
                <div className="flex items-start gap-4">
                  <div className="flex flex-col items-center">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-600 text-sm font-bold text-white">
                      {idx + 1}
                    </div>
                    <span className="mt-1 text-[10px] text-slate-400">STEP</span>
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-base font-bold text-slate-900">{item.category}</span>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">
                        실무 랭킹 {item.order}위
                      </span>
                    </div>

                    {/* 왜 먼저 봐야 하는지 — 백엔드가 만든 선정 근거(reason) */}
                    <p className="mt-1 text-xs text-indigo-600">📌 선정 근거: {item.reason}</p>

                    <div className="mt-3 space-y-2">
                      <SectionLabel>대표 질문</SectionLabel>
                      <p className="text-sm text-slate-700">"{item.questionExample}"</p>
                      <SectionLabel>답변</SectionLabel>
                      {item.answer ? (
                        <p className="whitespace-pre-line rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">
                          {item.answer}
                        </p>
                      ) : (
                        <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-400">
                          아직 축적된 답변이 없습니다. 통합 검색에서 이 질문이 응답되면 여기에 표시됩니다.
                        </p>
                      )}
                    </div>

                    <button
                      onClick={() =>
                        setDone((prev) => ({ ...prev, [item.order]: !prev[item.order] }))
                      }
                      className={`mt-3 rounded-lg px-4 py-1.5 text-sm font-semibold ${
                        done[item.order]
                          ? 'border border-slate-300 text-slate-500'
                          : 'bg-emerald-600 text-white hover:bg-emerald-500'
                      }`}
                    >
                      {done[item.order] ? '학습 완료됨 ✓' : '학습 완료로 표시'}
                    </button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}

      <p className="mt-5 rounded-lg bg-slate-100 p-3 text-xs text-slate-500">
        🔄 선순환: 신규입사자의 질의도 DB에 누적되어 다음 랭킹에 반영됩니다. 기간이 바뀌면 위 학습
        순서도 자동으로 최신화됩니다.
      </p>
    </div>
  )
}
