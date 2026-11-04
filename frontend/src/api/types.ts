/** 프론트가 쓰는 백엔드 인터페이스. http.ts(실서버)와 mock.ts(샘플)가 같은 모양으로 구현한다. */
import type { Card, CardFields, Document, ExportRecord, Job } from '../types/domain'

export interface SourceOption {
  key: string
  title: string
  url: string
  date: string
  sentence_count: number
}

export interface DocumentIn {
  text: string
  title?: string | null
  source_url?: string | null
  source_name?: string | null
  license?: string | null
}

export interface StartedJob {
  document_id: string
  job_id: string
}

export class ApiError extends Error {
  code: number
  constructor(code: number, message: string) {
    super(message)
    this.code = code
  }
}

export interface CardSyncApi {
  readonly mode: 'http' | 'mock'
  health(): Promise<{ status: string; openai_key_configured: boolean }>
  /** 원문 입력 화면의 추천 목록 (mock은 샘플, http는 빈 목록) */
  sources(): Promise<SourceOption[]>
  /** 추천 목록에서 고른 원문의 본문 텍스트 (http는 없음) */
  sourceText(key: string): Promise<DocumentIn | null>
  createDocument(body: DocumentIn): Promise<StartedJob>
  getJob(jobId: string): Promise<Job>
  getDocument(documentId: string): Promise<Document>
  putSelection(documentId: string, groupIds: string[]): Promise<{ cards_outdated: boolean }>
  createCards(documentId: string, overwrite: boolean): Promise<StartedJob>
  listCards(documentId: string): Promise<Card[]>
  patchCard(documentId: string, cardId: string, expectedVersion: number, fields: Partial<CardFields>): Promise<Card>
  createChecks(documentId: string, cardIds?: string[]): Promise<{ job_id: string; card_ids: string[] }>
  record(documentId: string): Promise<ExportRecord>
}

/** 작업이 끝날 때까지 폴링한다. onStage로 단계명을 알려준다. */
export async function waitJob(
  api: CardSyncApi,
  jobId: string,
  onStage?: (stage: string | null) => void,
  intervalMs = 700,
): Promise<Job> {
  for (;;) {
    const job = await api.getJob(jobId)
    onStage?.(job.stage)
    if (job.status === 'succeeded') return job
    if (job.status === 'failed') throw new ApiError(500, `작업 실패 (${job.error?.stage ?? '?'}: ${job.error?.type ?? '?'})`)
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}
