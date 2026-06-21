import type { ReactNode } from 'react'
import type { Article } from '../data/mock'
import type { NoticeDocType } from '../api/types'

const typeColor: Record<NoticeDocType, string> = {
  규정: 'bg-indigo-100 text-indigo-700',
  지침: 'bg-emerald-100 text-emerald-700',
  절차: 'bg-amber-100 text-amber-700',
  공고: 'bg-sky-100 text-sky-700',
  참고자료: 'bg-fuchsia-100 text-fuchsia-700',
}

export function TypeBadge({ type }: { type: NoticeDocType }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${typeColor[type]}`}>
      {type}
    </span>
  )
}

// 청크 content_type → 사람이 읽는 한국어 라벨. 목록에 없는 값(PDF 등)은 태그를 표시하지 않는다.
const CONTENT_TYPE_LABEL: Record<string, string> = {
  text: '본문',
  paragraph: '본문',
  'list-item': '목록',
  list_item: '목록',
  'table-row': '표',
  table_row: '표',
  'table-note': '표 주석',
  table_note: '표 주석',
  infographic: '그림',
  figure: '그림',
  heading: '제목',
  warning: '주의',
  footnote: '각주',
}

/**
 * 유형 태그. 규정/지침/절차(문서 종류)는 색상 배지로, 청크 content_type 은 한국어 라벨로,
 * 그 외(PDF 등 알 수 없는 값)는 아무것도 표시하지 않는다 — 영문 속성값이 그대로 노출되지 않도록.
 */
function KindTag({ docType }: { docType: string }) {
  if (docType in typeColor) {
    return <TypeBadge type={docType as NoticeDocType} />
  }
  const label = CONTENT_TYPE_LABEL[docType]
  if (!label) return null
  return (
    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-500">
      {label}
    </span>
  )
}

/** 출처(문서명·조항) 칩 — 모든 답변에 출처를 명시한다는 핵심 규칙 구현 */
export function SourceChip({ article }: { article: Article }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-600">
      <KindTag docType={article.docType} />
      {article.docTitle}
      {article.articleNo ? ` · ${article.articleNo}` : ''}
    </span>
  )
}

/**
 * 근거 조항 본문(embedding_text)은 불릿·"(출처: …)" 꼬리표가 한 줄로 평탄화되어 있다.
 * 가독성을 위해 (1) 끝의 "(출처: …)" 를 분리하고 (2) 불릿(•·※·○)·"- " 리스트 항목마다 줄바꿈한다.
 */
function splitArticleText(raw: string): { lines: string[]; source: string | null } {
  let body = (raw ?? '').trim()
  let source: string | null = null

  const i = body.lastIndexOf('(출처:')
  if (i >= 0) {
    source = body.slice(i).replace(/^\(\s*/, '').replace(/\)\s*$/, '').trim()
    body = body.slice(0, i).trim()
  }

  const withBreaks = body
    .replace(/\s*([•※○])\s*/g, '\n$1 ') // 불릿 앞에서 줄바꿈
    .replace(/(^|\s)-\s+/g, '\n- ') // "- " 리스트 항목 앞에서 줄바꿈
  const lines = withBreaks
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)

  return { lines: lines.length ? lines : body ? [body] : [], source }
}

/**
 * 근거 조항 카드. 본문(조항 내용)을 위에, 유형 태그·출처(문서명·페이지·heading)는
 * 하단에 연한 글씨로 둔다. 파일명은 제목이 아니라 출처로만 노출된다.
 */
export function ArticleCard({ article }: { article: Article }) {
  const { lines, source } = splitArticleText(article.text)
  const sourceLine =
    source ?? `출처: ${article.docTitle}${article.articleNo ? ` · ${article.articleNo}` : ''}`
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="space-y-1 text-sm leading-relaxed text-slate-700">
        {lines.map((line, i) => (
          <p key={i}>{line}</p>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2">
        <KindTag docType={article.docType} />
        <span className="text-xs text-slate-400">{sourceLine}</span>
      </div>
    </div>
  )
}

export function PageHeader({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
      <p className="mt-1 text-sm text-slate-500">{desc}</p>
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
      {children}
    </div>
  )
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">{children}</h2>
  )
}
