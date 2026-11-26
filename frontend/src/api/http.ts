/** FastAPI 백엔드(/api/v1) 클라이언트. 응답 형식은 {code, message, data}. */
import type { Card, CardFields, Document, ExportRecord, Job } from '../types/domain'
import { ApiError, type CardSyncApi, type DocumentIn, type SourceOption, type StartedJob } from './types'

interface Envelope<T> {
  code: number
  message: string
  data?: T
}

/** 백엔드 검사 결과는 problems[{quote, reason}] 이고 summary 가 없다. 화면이 쓰는 issues 모양으로 맞춘다. */
/**
 * 백엔드 검사 결과를 화면 모양으로 맞춘다.
 * - 카드 단계(기본): issues·completeness·repair_fields 가 온다 → repair_fields 는 카드의 repair(AI 수정안)로
 * - 요약 단계(stage=summary): problems[{quote, reason}] 만 온다 → issues 로 변환
 */
function normalizeCard(c: Card & { check?: (Card['check'] & { problems?: { quote: string; reason: string }[] }) | null }): Card {
  const check = c.check
  if (!check) return { ...c, repair: null }
  const problems = check.problems ?? []
  const issues = check.issues ?? problems.map((p) => ({ type: '원문과 다름', source_span: '', card_span: p.quote, explanation: p.reason }))
  const completeness = check.completeness ?? []
  const summary =
    check.summary ??
    (check.verdict === 'ok'
      ? completeness.length
        ? '문구는 요약과 맞지만 필수 정보 반영을 확인해 주세요.'
        : '카드 문구가 근거 요약으로 뒷받침돼요.'
      : `요약과 다른 부분이 ${issues.length}곳 있어요.`)
  const repair = check.repair_fields ? { fields: check.repair_fields, check: { ...check, issues, summary } } : null
  return { ...c, check: { ...check, issues, completeness, summary }, repair }
}

export function createHttpApi(base: string): CardSyncApi {
  const root = `${base.replace(/\/$/, '')}/api/v1`

  async function call<T>(path: string, init?: RequestInit): Promise<T> {
    let res: Response
    try {
      // 본문이 있을 때만 JSON 헤더를 붙인다. GET에 붙이면 매 요청 CORS 사전 요청(OPTIONS)이 생긴다
      res = await fetch(root + path, {
        ...init,
        headers: { ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...(init?.headers ?? {}) },
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
    listCards: async (id) => (await call<{ cards: Card[] }>(`/documents/${id}/cards`)).cards.map(normalizeCard),
    patchCard: async (id, cardId, expectedVersion, fields: Partial<CardFields>) =>
      normalizeCard(
        (
          await call<{ card: Card }>(`/documents/${id}/cards/${cardId}`, {
            method: 'PATCH',
            body: JSON.stringify({ expected_version: expectedVersion, ...fields }),
          })
        ).card,
      ),
    createChecks: (id, cardIds) =>
      call(`/documents/${id}/checks`, { method: 'POST', body: JSON.stringify(cardIds ? { card_ids: cardIds } : {}) }),
    record: async (id) => {
      const r = await call<ExportRecord>(`/documents/${id}/record`)
      return { ...r, cards: r.cards.map(normalizeCard) }
    },
  }
}
