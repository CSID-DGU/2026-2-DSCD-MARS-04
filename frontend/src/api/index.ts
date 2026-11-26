/**
 * API 선택. VITE_API_MODE=mock 이면 샘플, 아니면 백엔드(VITE_API_BASE, 기본 http://localhost:8000).
 * 백엔드 health 가 실패하면 mock 으로 내려간다 (resolveApi).
 */
import { createHttpApi } from './http'
import { createMockApi } from './mock'
import type { CardSyncApi } from './types'

export * from './types'

const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const MODE = import.meta.env.VITE_API_MODE || 'auto'

export async function resolveApi(): Promise<{ api: CardSyncApi; fallback: boolean }> {
  if (MODE === 'mock') return { api: createMockApi(), fallback: false }
  const http = createHttpApi(BASE)
  try {
    await http.health()
    return { api: http, fallback: false }
  } catch {
    if (MODE === 'http') throw new Error(`백엔드(${BASE})에 연결할 수 없어요.`)
    return { api: createMockApi(), fallback: true }
  }
}
