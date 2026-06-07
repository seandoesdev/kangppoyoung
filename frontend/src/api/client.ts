// 백엔드 호출 공통 클라이언트.
// 모든 API 함수는 이 client 를 거쳐 서버와 통신한다 (베이스 경로·에러 처리·직렬화 일원화).

import type { ApiErrorBody } from './types'

// OpenAPI servers[0].url 과 동일. 배포 환경에 따라 VITE_API_BASE_URL 로 덮어쓴다.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

/** 서버가 4xx/5xx 를 반환했을 때 던지는 에러. 가능하면 본문의 code/message 를 담는다. */
export class ApiError extends Error {
  readonly status: number
  readonly code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

type Query = Record<string, string | number | boolean | undefined>

function buildUrl(path: string, query?: Query): string {
  const url = `${BASE_URL}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.append(key, String(value))
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

async function toError(res: Response): Promise<ApiError> {
  let message = res.statusText
  let code: string | undefined
  try {
    const body = (await res.json()) as Partial<ApiErrorBody>
    if (body?.message) message = body.message
    if (body?.code) code = body.code
  } catch {
    // 본문이 JSON 이 아니거나 비어 있으면 statusText 를 사용한다.
  }
  return new ApiError(res.status, message, code)
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) throw await toError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const http = {
  get<T>(path: string, query?: Query, init?: RequestInit): Promise<T> {
    return fetch(buildUrl(path, query), { ...init, method: 'GET' }).then(parse<T>)
  },

  post<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return fetch(buildUrl(path), {
      ...init,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then(parse<T>)
  },

  /** multipart/form-data 업로드 (Content-Type 은 브라우저가 boundary 와 함께 자동 설정). */
  postForm<T>(path: string, form: FormData, init?: RequestInit): Promise<T> {
    return fetch(buildUrl(path), { ...init, method: 'POST', body: form }).then(parse<T>)
  },

  delete<T = void>(path: string, init?: RequestInit): Promise<T> {
    return fetch(buildUrl(path), { ...init, method: 'DELETE' }).then(parse<T>)
  },
}
