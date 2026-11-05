/** 백엔드(backend/services/workflow.py, data_pipeline/schemas)와 맞춘 도메인 타입. */

export type LayoutId = 'cover' | 'body' | 'checklist' | 'steps' | 'compare' | 'closing'

export const LAYOUT_NAME: Record<LayoutId, string> = {
  cover: '표지',
  body: '본문',
  checklist: '체크리스트',
  steps: '단계',
  compare: '비교',
  closing: '마무리',
}

export interface SourceMeta {
  title: string | null
  source_url: string | null
  source_name: string | null
  license: string | null
  date?: string | null
}

export interface Sentence {
  sentence_id: string
  text: string
}

/** 요약 단계 검사(그룹 문장 ↔ 그룹 요약) 결과. 백엔드 분석 단계에서 붙는다. */
export interface SummaryCheck {
  verdict: 'ok' | 'bad' | 'error'
  by: 'rule' | 'llm' | null
  problems: { quote: string; reason: string }[]
  checker: string
  error?: string
}

export interface Group {
  group_id: string
  sentence_ids: string[]
  summary: string
  topic: string
  headline: string
  summary_check?: SummaryCheck | null
}

export interface SourceImage {
  url: string
  caption: string
  reason: string
}

export interface CompareSide {
  label: string
  value: string
}

/** 사용자가 편집할 수 있는 카드 문구 필드 */
export interface CardFields {
  title: string
  category?: string | null
  body?: string | null
  items?: string[] | null
  left?: CompareSide | null
  right?: CompareSide | null
  cta?: string | null
}

export const CARD_FIELD_KEYS = ['category', 'title', 'body', 'cta', 'items', 'left', 'right'] as const

export type ImageStage = 'unsplash' | 'upload' | 'none'

export interface CardImage {
  stage: ImageStage
  /** 이미지 URL 또는 data URL */
  data?: string
  id?: string
  query?: string
  alt?: string
  author?: string
  author_url?: string
  photo_url?: string
  license?: string
  message?: string
}

export type Verdict = 'ok' | 'warn' | 'bad'
export type CardStatus = Verdict | 'pending' | 'unchecked'

export interface CheckIssue {
  type: string
  source_span: string
  card_span: string
  explanation: string
  field_path?: string
  suggested_text?: string | null
}

/** 완전성 검사: 선택한 그룹의 필수 정보가 카드 전체에 반영됐는지 */
export interface CompletenessIssue {
  type: string
  fact_id: string
  explanation: string
  missing_elements: string[]
}

export interface FeedbackItem {
  title: string
  category: 'ERROR' | 'OMISSION' | 'REVIEW'
  description: string
  suggested_text: string | null
  card_ids: string[]
}

export interface CheckResult {
  card_id: string
  card_version?: number
  verdict: Verdict
  summary: string
  issues: CheckIssue[]
  /** 글자 수 한도 초과 필드 */
  lint?: string[]
  by?: string | null
  checker?: string
  /** 카드 단계 검사(백엔드)에서만 */
  factuality_status?: string
  completeness?: CompletenessIssue[]
  repair_fields?: Partial<CardFields> | null
  feedback?: FeedbackItem[]
}

export interface Repair {
  fields: Partial<CardFields>
  check: CheckResult
  lint?: string[]
}

export interface Card extends CardFields {
  card_id: string
  layout_id: LayoutId
  group_id: string | null
  sids: string[]
  image_query: string
  order: number
  version: number
  status: CardStatus
  check: CheckResult | null
  image?: CardImage
  /** 샘플 데이터에만 있는 AI 수정안 (백엔드 repair API는 준비 중) */
  repair?: Repair | null
}

export interface Document {
  document_id: string
  status: string
  source: SourceMeta
  sentences: Sentence[]
  groups: Group[]
  required_group_ids: string[]
  source_images?: SourceImage[]
}

export interface Job {
  job_id: string
  kind: 'analysis' | 'generation' | 'check'
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  stage: string | null
  document_id: string
  error: { type: string; stage: string | null } | null
  elapsed_seconds: number | null
}

export interface ExportRecord {
  exported_at: string
  document_id: string
  source: SourceMeta
  sentences: Sentence[]
  groups: (Group & { selected: boolean })[]
  cards: Card[]
  unverified_card_count: number
}
