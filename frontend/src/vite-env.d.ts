/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 백엔드 API 베이스 경로. 미설정 시 OpenAPI servers 기본값(/api/v1) 사용. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
