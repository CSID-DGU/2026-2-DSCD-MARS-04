/** FastAPI 백엔드(/api/v1) 클라이언트. 응답 형식은 {code, message, data}. */
import type { Card, CardFields, Document, ExportRecord, Job } from '../types/domain'
import { ApiError, type CardSyncApi, type DocumentIn, type SourceOption, type StartedJob } from './types'

interface Envelope<T> {
  code: number
  message: string
  data?: T
}

export function createHttpApi(base: string): CardSyncApi {
  const root = `${base.replace(/\/$/, '')}/api/v1`

  async function call<T>(path: string, init?: RequestInit): Promise<T> {
    let res: Response
    try {
      res = await fetch(root + path, {
        ...init,
        headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      })
    } catch {
      throw new ApiError(0, '서버에 연결할 수 없어요. 백엔드가 켜져 있는지 확인해 주세요.')
    }
    const body = (await res.json().catch(() => ({}))) as Envelope<T>
    if (!res.ok) throw new ApiError(res.status, body.message ?? `요청 실패 (${res.status})`)
    return body.data as T
  }

  return {
    mode: 'http',
    health: () => call('/health'),
    sources: async (): Promise<SourceOption[]> => [],
    sourceText: async () => null,
    createDocument: (body: DocumentIn) =>
      call<StartedJob>('/documents', { method: 'POST', body: JSON.stringify(body) }),
    getJob: (jobId) => call<Job>(`/jobs/${jobId}`),
    getDocument: (id) => call<Document>(`/documents/${id}`),
    putSelection: (id, groupIds) =>
      call(`/documents/${id}/selection`, { method: 'PUT', body: JSON.stringify({ required_group_ids: groupIds }) }),
    createCards: (id, overwrite) =>
      call<StartedJob>(`/documents/${id}/cards?overwrite=${overwrite}`, { method: 'POST' }),
    listCards: async (id) => (await call<{ cards: Card[] }>(`/documents/${id}/cards`)).cards,
    patchCard: async (id, cardId, expectedVersion, fields: Partial<CardFields>) =>
      (
        await call<{ card: Card }>(`/documents/${id}/cards/${cardId}`, {
          method: 'PATCH',
          body: JSON.stringify({ expected_version: expectedVersion, ...fields }),
        })
      ).card,
    createChecks: (id, cardIds) =>
      call(`/documents/${id}/checks`, { method: 'POST', body: JSON.stringify(cardIds ? { card_ids: cardIds } : {}) }),
    record: (id) => call<ExportRecord>(`/documents/${id}/record`),
  }
}
