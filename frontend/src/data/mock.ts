// 정책자금 지원 업무 플랫폼 — 유저 플로우 검증용 목업 데이터
// (정책문서 목록 + 검색 시나리오. UC-4 질문 분석/UC-5 온보딩은 실 API 연동으로 전환되어 목 제거됨.)

export type DocType = '규정' | '지침' | '절차'

export interface PolicyDocument {
  id: string
  title: string
  type: DocType
  updatedAt: string
  /** 단일 진실 문서 여부 (UC-3) */
  isSingleSource: boolean
}

export interface Article {
  docId: string
  docTitle: string
  docType: DocType
  articleNo: string // 예: 제5조 2항
  text: string
}

/** UC-1 검색 결과: 근거 + 중복(요약) / 상충(원문 병렬) */
export interface SearchResult {
  query: string
  answer: string
  /** 답변의 직접 근거 조항 */
  evidence: Article[]
  /** 중복 절차: 하나로 요약 + 출처 */
  duplicateSummary?: {
    summary: string
    sources: Article[]
  }
  /** 상충 절차: 원문 그대로 병렬 + 출처 */
  conflicts?: Article[]
}

export const DOCUMENTS: PolicyDocument[] = [
  { id: 'D-001', title: '정책자금 융자 운용 규정', type: '규정', updatedAt: '2026-05-28', isSingleSource: true },
  { id: 'D-002', title: '신청 자격 심사 지침', type: '지침', updatedAt: '2026-05-30', isSingleSource: true },
  { id: 'D-003', title: '서류 제출 및 접수 절차', type: '절차', updatedAt: '2026-06-01', isSingleSource: true },
  { id: 'D-004', title: '대출 한도 산정 지침', type: '지침', updatedAt: '2026-04-12', isSingleSource: true },
  { id: 'D-005', title: '상환 및 연체 관리 절차', type: '절차', updatedAt: '2026-05-15', isSingleSource: true },
  { id: 'D-006', title: '구(舊) 서류 접수 안내 (통합 전)', type: '절차', updatedAt: '2025-11-02', isSingleSource: false },
]

const A = (
  docId: string,
  docTitle: string,
  docType: DocType,
  articleNo: string,
  text: string,
): Article => ({ docId, docTitle, docType, articleNo, text })

/** 미리 정의된 검색 시나리오 (자연어 질의 → 근거) */
export const SEARCH_SCENARIOS: SearchResult[] = [
  {
    query: '서류 제출 기한이 어떻게 되나요?',
    answer:
      '서류 제출 기한은 접수 마감일로부터 영업일 기준 5일 이내입니다. 동일 내용이 두 문서에 중복 기재되어 있어 하나로 요약했습니다.',
    evidence: [
      A('D-003', '서류 제출 및 접수 절차', '절차', '제4조 1항', '신청 서류는 접수 마감일로부터 영업일 기준 5일 이내에 제출하여야 한다.'),
    ],
    duplicateSummary: {
      summary: '서류 제출 기한 = 접수 마감일 기준 영업일 5일 이내 (두 문서 내용 동일).',
      sources: [
        A('D-003', '서류 제출 및 접수 절차', '절차', '제4조 1항', '신청 서류는 접수 마감일로부터 영업일 기준 5일 이내에 제출하여야 한다.'),
        A('D-001', '정책자금 융자 운용 규정', '규정', '제12조', '제출 서류는 접수 마감 후 5영업일 이내 제출을 원칙으로 한다.'),
      ],
    },
  },
  {
    query: '대출 한도는 매출액 기준인가요 자기자본 기준인가요?',
    answer:
      '두 지침이 서로 다른 기준을 제시하고 있어 상충됩니다. 임의 통합 없이 원문을 그대로 병렬 표시합니다. 적용 기준은 담당 부서 확인이 필요합니다.',
    evidence: [],
    conflicts: [
      A('D-004', '대출 한도 산정 지침', '지침', '제3조', '대출 한도는 직전 연도 매출액의 30% 이내로 산정한다.'),
      A('D-001', '정책자금 융자 운용 규정', '규정', '제8조 2항', '대출 한도는 자기자본의 200% 범위 내에서 산정한다.'),
    ],
  },
  {
    query: '연체 시 어떤 절차가 진행되나요?',
    answer:
      '연체 발생 시 1차 안내(7일) → 2차 독촉(15일) → 기한이익 상실 순으로 진행됩니다.',
    evidence: [
      A('D-005', '상환 및 연체 관리 절차', '절차', '제6조', '연체 발생일로부터 7일 이내 1차 안내, 15일 경과 시 2차 독촉을 시행한다.'),
      A('D-005', '상환 및 연체 관리 절차', '절차', '제7조', '2차 독촉 후에도 미상환 시 기한이익 상실 처리한다.'),
    ],
  },
]
