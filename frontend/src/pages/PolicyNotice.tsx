import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import type {
  ContentBlock,
  DiffBlock,
  NoticeCategory,
  NoticeCategoryKey,
  NoticeVersion,
} from '../api/types'
import {
  getNotice,
  getNoticeVersionDiff,
  preprocessNoticePdf,
  registerNoticeRevision,
  uploadNoticeAsset,
} from '../api/notices'
import { ApiError, assetSrc } from '../api/client'
import { Card, PageHeader, TypeBadge } from '../components/ui'

const MAX_PDF_BYTES = 50 * 1024 * 1024 // 50MB (백엔드 app.preprocess.max-bytes 와 이중)

const errMsg = (e: unknown, fallback: string): string =>
  e instanceof ApiError ? e.message : fallback

export default function PolicyNotice() {
  const params = useParams()
  const category = (params.category as NoticeCategoryKey) ?? 'regulation'

  // 공고 문서(카테고리) + 버전 목록 — 백엔드 GET /notices/{category} 로 로드.
  const [notice, setNotice] = useState<NoticeCategory | null>(null)
  const [selected, setSelected] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showRegister, setShowRegister] = useState(false)

  // 변경 사항(diff) — 백엔드 LCS 계산(바로 전 버전 대비).
  const [diff, setDiff] = useState<DiffBlock[] | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [diffError, setDiffError] = useState<string | null>(null)

  const reload = useCallback(
    async (selectLatest: boolean) => {
      setLoading(true)
      setError(null)
      try {
        const data = await getNotice(category)
        setNotice(data)
        if (selectLatest) setSelected(0)
      } catch (e) {
        setNotice(null)
        setError(errMsg(e, '공고를 불러오지 못했습니다.'))
      } finally {
        setLoading(false)
      }
    },
    [category],
  )

  // 카테고리(라우트) 변경 시 재로드 + 상태 초기화
  useEffect(() => {
    setSelected(0)
    setShowRegister(false)
    reload(true)
  }, [category, reload])

  const versions = notice?.versions ?? []
  const current: NoticeVersion | undefined = versions[selected]
  const previous: NoticeVersion | undefined = versions[selected + 1] // 바로 전(더 오래된) 버전

  // 선택 버전이 바뀌면 백엔드에 diff 요청(이전 버전이 있을 때만). stale 응답은 폐기.
  useEffect(() => {
    if (!current || !previous) {
      setDiff(null)
      setDiffError(null)
      setDiffLoading(false)
      return
    }
    let live = true
    setDiffLoading(true)
    setDiffError(null)
    getNoticeVersionDiff(category, current.version)
      .then((d) => {
        if (live) setDiff(d)
      })
      .catch((e) => {
        if (!live) return
        setDiff(null)
        setDiffError(errMsg(e, '변경 사항을 불러오지 못했습니다.'))
      })
      .finally(() => {
        if (live) setDiffLoading(false)
      })
    return () => {
      live = false
    }
  }, [category, current?.version, previous?.version])

  async function handleRegister(date: string, blocks: ContentBlock[]) {
    // 실패 시 throw → 모달이 잡아서 에러를 표시하고 열린 채로 유지.
    await registerNoticeRevision(category, { effectiveDate: date, blocks })
    await reload(true) // 새 최신본이 versions[0]
    setShowRegister(false)
  }

  const label = notice?.label ?? (category === 'regulation' ? '공고' : '참고자료')
  const docTitle = notice?.docTitle ?? ''

  return (
    <div>
      <PageHeader
        title={`정책 자금 공고 · ${label}`}
        desc={`${docTitle || '문서'} — 개정 이력을 버전별로 조회하고, 바로 전 버전과의 변경 사항을 확인합니다.`}
      />

      {/* 툴바: 오른쪽 상단 버전 드랍박스 + 등록 버튼 */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TypeBadge type={notice?.docType ?? (category === 'reference' ? '참고자료' : '공고')} />
          <span className="text-sm font-semibold text-slate-700">{docTitle}</span>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selected}
            onChange={(e) => setSelected(Number(e.target.value))}
            disabled={versions.length === 0}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-900 disabled:opacity-50"
          >
            {versions.length === 0 ? (
              <option value={0}>버전 없음</option>
            ) : (
              versions.map((v, i) => (
                <option key={v.version + v.date} value={i}>
                  {v.date} · {v.version}
                  {i === 0 ? ' (최신)' : ''}
                </option>
              ))
            )}
          </select>
          <button
            onClick={() => setShowRegister(true)}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
          >
            + 개정본 등록
          </button>
        </div>
      </div>

      {/* 본문 + diff */}
      <Card>
        {loading ? (
          <p className="py-10 text-center text-sm text-slate-400">불러오는 중…</p>
        ) : error ? (
          <div className="rounded-lg border-l-4 border-rose-400 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
            <button
              onClick={() => reload(true)}
              className="ml-3 rounded border border-rose-300 px-2 py-0.5 text-xs font-semibold text-rose-600 hover:bg-white"
            >
              다시 시도
            </button>
          </div>
        ) : !current ? (
          <p className="py-10 text-center text-sm text-slate-400">
            등록된 버전이 없습니다 · 우측 상단 <b>+ 개정본 등록</b>으로 첫 버전을 등록하세요.
          </p>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm">
                <span className="font-bold text-slate-900">{current.version}</span>
                <span className="text-slate-400">시행일 {current.date}</span>
              </div>
              {previous ? (
                <span className="text-xs text-slate-400">
                  비교 기준: 바로 전 버전 {previous.version} ({previous.date})
                </span>
              ) : (
                <span className="text-xs text-slate-400">최초 등록본 · 비교 대상 없음</span>
              )}
            </div>

            {previous && (
              <div className="mb-3 flex gap-3 text-xs">
                <span className="inline-flex items-center gap-1 text-emerald-600">
                  <span className="inline-block h-3 w-3 rounded-sm bg-emerald-200" /> 추가
                </span>
                <span className="inline-flex items-center gap-1 text-rose-600">
                  <span className="inline-block h-3 w-3 rounded-sm bg-rose-200" /> 삭제
                </span>
              </div>
            )}

            {previous ? (
              diffLoading ? (
                <p className="py-6 text-center text-sm text-slate-400">변경 사항 계산 중…</p>
              ) : diffError ? (
                <div className="rounded-lg border-l-4 border-rose-400 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {diffError}
                </div>
              ) : (
                <div className="space-y-1">
                  {(diff ?? []).map((d, i) => (
                    <DiffRow key={i} diff={d} />
                  ))}
                </div>
              )
            ) : (
              <div className="space-y-1">
                {current.blocks.map((b, i) => (
                  <BlockView key={i} block={b} />
                ))}
              </div>
            )}
          </>
        )}
      </Card>

      {showRegister && (
        <RegisterModal
          category={category}
          docTitle={docTitle || label}
          previous={versions[0]}
          onClose={() => setShowRegister(false)}
          onSubmit={handleRegister}
        />
      )}
    </div>
  )
}

/** 본문 블록 1개 렌더 (텍스트/이미지) */
function BlockView({ block }: { block: ContentBlock }) {
  if (block.type === 'image') {
    return (
      <div className="px-2 py-1">
        <img
          src={assetSrc(block.src)}
          alt={block.name ?? '이미지'}
          className="max-h-64 rounded-lg border border-slate-200"
        />
        {block.name && <div className="mt-1 text-xs text-slate-400">{block.name}</div>}
      </div>
    )
  }
  return <div className="px-2 py-1 text-sm leading-relaxed text-slate-700">{block.text}</div>
}

function DiffRow({ diff }: { diff: DiffBlock }) {
  const { type, block } = diff
  if (type === 'same') {
    return (
      <div className="px-2 py-1">
        <BlockView block={block} />
      </div>
    )
  }
  const isAdd = type === 'add'
  return (
    <div
      className={`flex gap-2 rounded px-2 py-1 ${isAdd ? 'bg-emerald-50' : 'bg-rose-50'}`}
    >
      <span
        className={`select-none font-mono text-sm ${isAdd ? 'text-emerald-500' : 'text-rose-400'}`}
      >
        {isAdd ? '+' : '−'}
      </span>
      {block.type === 'image' ? (
        <div>
          <img
            src={assetSrc(block.src)}
            alt={block.name ?? '이미지'}
            className={`max-h-56 rounded-lg border ${
              isAdd ? 'border-emerald-300' : 'border-rose-300 opacity-70'
            }`}
          />
          {block.name && (
            <div className={`mt-1 text-xs ${isAdd ? 'text-emerald-600' : 'text-rose-500'}`}>
              {block.name}
            </div>
          )}
        </div>
      ) : (
        <span
          className={`text-sm leading-relaxed ${
            isAdd ? 'text-emerald-800' : 'text-rose-700 line-through'
          }`}
        >
          {block.text}
        </span>
      )}
    </div>
  )
}

// ── 등록 모달: PDF 업로드 → 전처리(백엔드) → 검토·승인 → 등록(백엔드) ──

type EditorBlock = ContentBlock & { id: number }

let blockId = 0

type Step = 'upload' | 'processing' | 'review'

function StepIndicator({ step }: { step: Step }) {
  const items: { key: Step; label: string }[] = [
    { key: 'upload', label: 'PDF 업로드' },
    { key: 'processing', label: '전처리' },
    { key: 'review', label: '검토·승인' },
  ]
  const order: Step[] = ['upload', 'processing', 'review']
  const cur = order.indexOf(step)
  return (
    <div className="flex items-center gap-1">
      {items.map((it, i) => (
        <div key={it.key} className="flex items-center">
          <span
            className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
              i <= cur ? 'bg-slate-900 text-white' : 'bg-slate-200 text-slate-400'
            }`}
          >
            {i + 1}
          </span>
          <span
            className={`ml-1.5 text-xs ${i <= cur ? 'font-semibold text-slate-700' : 'text-slate-400'}`}
          >
            {it.label}
          </span>
          {i < items.length - 1 && <span className="mx-2 text-slate-300">›</span>}
        </div>
      ))}
    </div>
  )
}

const keyOf = (b: ContentBlock): string => (b.type === 'text' ? `T:${b.text}` : `I:${b.src}`)

/** 검토 화면 왼쪽(이전 버전) 읽기 전용 블록 — 삭제된 항목은 빨강 */
function ReviewBlock({ block, tone }: { block: ContentBlock; tone: 'same' | 'del' }) {
  const del = tone === 'del'
  if (block.type === 'image') {
    return (
      <div className={`rounded-lg border p-2 ${del ? 'border-rose-200 bg-rose-50' : 'border-slate-100'}`}>
        <img
          src={assetSrc(block.src)}
          alt={block.name ?? '이미지'}
          className={`max-h-40 rounded border border-slate-200 ${del ? 'opacity-70' : ''}`}
        />
        {block.name && <div className="mt-1 text-xs text-slate-400">🖼 {block.name}</div>}
      </div>
    )
  }
  return (
    <div
      className={`rounded-lg border p-2 text-sm leading-relaxed ${
        del ? 'border-rose-200 bg-rose-50 text-rose-700 line-through' : 'border-slate-100 text-slate-700'
      }`}
    >
      {block.text}
    </div>
  )
}

function RegisterModal({
  category,
  docTitle,
  previous,
  onClose,
  onSubmit,
}: {
  category: NoticeCategoryKey
  docTitle: string
  previous?: NoticeVersion
  onClose: () => void
  onSubmit: (date: string, blocks: ContentBlock[]) => Promise<void>
}) {
  const [step, setStep] = useState<Step>('upload')
  const [fileName, setFileName] = useState('')
  const [procError, setProcError] = useState<string | null>(null)
  const [date, setDate] = useState('')
  const [blocks, setBlocks] = useState<EditorBlock[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [imgError, setImgError] = useState<string | null>(null)
  const [imgUploading, setImgUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const imageRef = useRef<HTMLInputElement>(null)
  // 진행 중 비동기(전처리/이미지 업로드) 응답이 도착하기 전에 모달이 닫히면 setState 를 건너뛴다.
  // 마운트 시 true 로 재설정해 StrictMode(개발) 이중 마운트에서도 가드가 영구 차단되지 않게 한다.
  const aliveRef = useRef(true)
  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
    }
  }, [])

  // PDF 선택 → 사전검증 → 백엔드 전처리(POST .../revisions/preprocess) → 검토 화면.
  async function pickPdf(files: FileList | null) {
    const f = files?.[0]
    if (!f) return
    if (f.type !== 'application/pdf') {
      setProcError('PDF 파일만 업로드할 수 있습니다.')
      return
    }
    if (f.size > MAX_PDF_BYTES) {
      setProcError('파일 크기는 50MB 이하여야 합니다.')
      return
    }
    setProcError(null)
    setFileName(f.name)
    setStep('processing')
    try {
      const res = await preprocessNoticePdf(category, f)
      if (!aliveRef.current) return
      setBlocks(res.blocks.map((b) => ({ ...b, id: blockId++ })))
      setStep('review')
    } catch (e) {
      if (!aliveRef.current) return
      setProcError(errMsg(e, '전처리 중 오류가 발생했습니다. 다시 시도하세요.'))
      setStep('upload')
    }
  }

  function addText() {
    setBlocks((prev) => [...prev, { id: blockId++, type: 'text', text: '' }])
  }

  async function addImages(files: FileList | null) {
    if (!files || files.length === 0) return
    setImgError(null)
    setImgUploading(true)
    try {
      for (const file of Array.from(files)) {
        // 수동 추가 이미지도 콘텐츠 주소 자산으로 업로드 → 전처리 이미지와 동일 규칙(diff 동등성·저장 일관성).
        const { url } = await uploadNoticeAsset(file)
        if (!aliveRef.current) return
        setBlocks((prev) => [...prev, { id: blockId++, type: 'image', src: url, name: file.name }])
      }
    } catch (e) {
      if (aliveRef.current) setImgError(errMsg(e, '이미지 업로드에 실패했습니다.'))
    } finally {
      if (aliveRef.current) setImgUploading(false)
    }
  }

  function updateText(id: number, text: string) {
    setBlocks((prev) => prev.map((b) => (b.id === id && b.type === 'text' ? { ...b, text } : b)))
  }

  function remove(id: number) {
    setBlocks((prev) => prev.filter((b) => b.id !== id))
  }

  function move(id: number, dir: -1 | 1) {
    setBlocks((prev) => {
      const idx = prev.findIndex((b) => b.id === id)
      const to = idx + dir
      if (idx < 0 || to < 0 || to >= prev.length) return prev
      const next = [...prev]
      ;[next[idx], next[to]] = [next[to], next[idx]]
      return next
    })
  }

  async function handleApprove() {
    // 개정본은 항상 새 최신본으로만 등록(과거 시행일 금지) — 백엔드 INVALID_EFFECTIVE_DATE 와 동일 규칙.
    if (previous && date < previous.date) {
      setSubmitError(`시행일은 현재 최신본(${previous.date}) 이후여야 합니다. 과거 시행일로는 등록할 수 없습니다.`)
      return
    }
    const clean: ContentBlock[] = blocks
      .map((b): ContentBlock =>
        b.type === 'text'
          ? { type: 'text', text: b.text.trim() }
          : { type: 'image', src: b.src, name: b.name },
      )
      .filter((b) => (b.type === 'text' ? b.text.length > 0 : true))
    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit(date, clean) // 성공 시 부모가 모달을 언마운트
    } catch (e) {
      setSubmitError(errMsg(e, '등록 중 오류가 발생했습니다.'))
      setSubmitting(false)
    }
  }

  const hasContent = blocks.some((b) => (b.type === 'text' ? b.text.trim().length > 0 : true))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        className={`flex max-h-[90vh] w-full flex-col rounded-xl bg-white shadow-xl ${
          step === 'review' ? 'max-w-5xl' : 'max-w-2xl'
        }`}
      >
        <div className="border-b border-slate-100 px-6 py-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-900">개정본 등록</h2>
            <StepIndicator step={step} />
          </div>
          <p className="mt-1 text-sm text-slate-500">{docTitle}</p>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {/* STEP 1. PDF 업로드 */}
          {step === 'upload' && (
            <div>
              <button
                onClick={() => fileRef.current?.click()}
                className="flex w-full flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 p-10 text-slate-400 hover:border-slate-900 hover:text-slate-600"
              >
                <span className="text-3xl">📄</span>
                <span className="mt-2 text-sm font-semibold">개정 PDF 파일 선택</span>
                <span className="mt-0.5 text-xs">PDF를 업로드하면 서버에서 자동으로 전처리됩니다. (최대 50MB)</span>
              </button>
              {procError && (
                <div className="mt-3 rounded-lg border-l-4 border-rose-400 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {procError}
                </div>
              )}
              <input
                ref={fileRef}
                type="file"
                accept="application/pdf,.pdf"
                hidden
                onChange={(e) => {
                  pickPdf(e.target.files)
                  e.target.value = ''
                }}
              />
            </div>
          )}

          {/* STEP 2. 전처리 진행 (백엔드 호출 대기) */}
          {step === 'processing' && (
            <div className="py-10">
              <div className="mx-auto flex max-w-sm flex-col items-center gap-3 text-center">
                <span className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
                <p className="text-sm text-slate-600">
                  <span className="font-semibold">{fileName}</span> 전처리 중…
                </p>
                <p className="text-xs text-slate-400">
                  PDF 텍스트·표·이미지를 추출합니다. 이미지 페이지가 많으면 시간이 걸릴 수 있습니다.
                </p>
              </div>
            </div>
          )}

          {/* STEP 3. 검토 · 승인 — 이전 버전 ↔ 갱신본 나란히 비교(diff) */}
          {step === 'review' &&
            (() => {
              const prevBlocks = previous?.blocks ?? []
              const prevKeys = new Set(prevBlocks.map(keyOf))
              const newKeys = new Set(blocks.map((b) => keyOf(b)))
              return (
                <div className="space-y-4">
                  <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
                    ✅ <b>{fileName}</b> 전처리 완료. 이전 버전과 갱신본을 비교해 확인하고, 필요 시
                    수정한 뒤 등록을 승인하세요.
                  </div>

                  <div className="flex flex-wrap items-end justify-between gap-3">
                    <div className="flex items-center gap-3 text-xs">
                      <span className="inline-flex items-center gap-1 text-emerald-600">
                        <span className="inline-block h-3 w-3 rounded-sm bg-emerald-200" /> 추가
                      </span>
                      <span className="inline-flex items-center gap-1 text-rose-600">
                        <span className="inline-block h-3 w-3 rounded-sm bg-rose-200" /> 삭제
                      </span>
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-semibold text-slate-500">
                        시행일
                      </label>
                      <input
                        type="date"
                        value={date}
                        min={previous?.date}
                        onChange={(e) => setDate(e.target.value)}
                        className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                      />
                      {previous && (
                        <p className="mt-1 text-xs text-slate-400">
                          현재 최신본({previous.date}) 이후 날짜만 등록할 수 있습니다.
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    {/* 왼쪽: 이전 버전 (읽기 전용, 삭제=빨강) */}
                    <div className="rounded-lg border border-slate-200">
                      <div className="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-500">
                        {previous
                          ? `이전 버전 · ${previous.version} (${previous.date})`
                          : '이전 버전 없음 (최초 등록)'}
                      </div>
                      <div className="space-y-1 p-3">
                        {prevBlocks.length === 0 && (
                          <p className="py-6 text-center text-xs text-slate-400">
                            비교할 이전 버전이 없습니다.
                          </p>
                        )}
                        {prevBlocks.map((b, i) => {
                          const removed = !newKeys.has(keyOf(b))
                          return <ReviewBlock key={i} block={b} tone={removed ? 'del' : 'same'} />
                        })}
                      </div>
                    </div>

                    {/* 오른쪽: 갱신본 (편집 가능, 추가=초록) */}
                    <div className="rounded-lg border border-slate-200">
                      <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-3 py-2">
                        <span className="text-xs font-bold text-slate-500">갱신본 (등록 예정)</span>
                        <div className="flex gap-1">
                          <button
                            onClick={addText}
                            className="rounded border border-slate-300 px-2 py-0.5 text-xs font-semibold text-slate-600 hover:bg-white"
                          >
                            + 텍스트
                          </button>
                          <button
                            onClick={() => imageRef.current?.click()}
                            disabled={imgUploading}
                            className="rounded border border-slate-300 px-2 py-0.5 text-xs font-semibold text-slate-600 hover:bg-white disabled:opacity-50"
                          >
                            {imgUploading ? '업로드 중…' : '+ 이미지'}
                          </button>
                          <input
                            ref={imageRef}
                            type="file"
                            accept="image/*"
                            multiple
                            hidden
                            onChange={(e) => {
                              addImages(e.target.files)
                              e.target.value = ''
                            }}
                          />
                        </div>
                      </div>
                      {imgError && (
                        <div className="border-b border-rose-100 bg-rose-50 px-3 py-1.5 text-xs text-rose-600">
                          {imgError}
                        </div>
                      )}
                      <div className="space-y-2 p-3">
                        {blocks.length === 0 && (
                          <p className="py-6 text-center text-xs text-slate-400">
                            내용이 없습니다. 텍스트/이미지를 추가하세요.
                          </p>
                        )}
                        {blocks.map((b) => {
                          const added = !prevKeys.has(keyOf(b))
                          return (
                            <div
                              key={b.id}
                              className={`flex items-start gap-2 rounded-lg border p-2 ${
                                added ? 'border-emerald-200 bg-emerald-50' : 'border-slate-100 bg-white'
                              }`}
                            >
                              <div className="flex flex-col gap-0.5 pt-1">
                                <button
                                  onClick={() => move(b.id, -1)}
                                  className="h-5 w-5 rounded text-xs text-slate-400 hover:bg-slate-100"
                                  aria-label="위로"
                                >
                                  ↑
                                </button>
                                <button
                                  onClick={() => move(b.id, 1)}
                                  className="h-5 w-5 rounded text-xs text-slate-400 hover:bg-slate-100"
                                  aria-label="아래로"
                                >
                                  ↓
                                </button>
                              </div>
                              <div className="flex-1">
                                {b.type === 'text' ? (
                                  <textarea
                                    value={b.text}
                                    onChange={(e) => updateText(b.id, e.target.value)}
                                    rows={2}
                                    placeholder="조항/문단 내용을 입력하세요"
                                    className="w-full resize-y rounded border border-slate-200 bg-white px-2 py-1.5 text-sm outline-none focus:border-slate-900"
                                  />
                                ) : (
                                  <div>
                                    <img
                                      src={assetSrc(b.src)}
                                      alt={b.name ?? '이미지'}
                                      className="max-h-40 rounded border border-slate-200"
                                    />
                                    <div className="mt-1 text-xs text-slate-400">🖼 {b.name}</div>
                                  </div>
                                )}
                              </div>
                              <button
                                onClick={() => remove(b.id)}
                                className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-rose-50 hover:text-rose-500"
                              >
                                삭제
                              </button>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })()}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-slate-100 px-6 py-4">
          <button
            onClick={onClose}
            disabled={submitting}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            취소
          </button>
          {step === 'review' && (
            <div className="flex items-center gap-2">
              {submitError && <span className="text-xs text-rose-600">{submitError}</span>}
              <button
                onClick={() => {
                  setStep('upload')
                  setSubmitError(null)
                }}
                disabled={submitting}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                다시 업로드
              </button>
              <button
                onClick={handleApprove}
                disabled={!date || !hasContent || submitting}
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-40"
              >
                {submitting ? '등록 중…' : '승인 후 등록'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
