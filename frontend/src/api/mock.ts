/** 백엔드 없이 샘플 데이터로 동작하는 모의 API. 동작·지연·응답 형태를 실서버와 맞춘다. */
import { SAMPLES, type Sample } from '../data/samples'
import type { Card, CardFields, CheckResult, Document, ExportRecord, Job } from '../types/domain'
import { CARD_FIELD_KEYS } from '../types/domain'
import { ApiError, type CardSyncApi, type DocumentIn, type SourceOption, type StartedJob } from './types'

const DELAY = { analysis: 2000, generation: 4000, check: 3000 }
const STAGES: Record<Job['kind'], string[]> = {
  analysis: ['split', 'analysis', 'titles'],
  generation: ['cards', 'images', 'layout'],
  check: ['evidence', 'check', 'verdict'],
}

interface State {
  sample: Sample
  document: Document
  cards: Card[]
  selectionVersion: number
  cardsSelectionVersion: number | null
}

const clone = <T,>(o: T): T => JSON.parse(JSON.stringify(o))
const pickFields = (c: CardFields): Partial<CardFields> => {
  const o: Partial<CardFields> = {}
  for (const k of CARD_FIELD_KEYS) {
    const v = c[k]
    if (v !== undefined && v !== null) (o as Record<string, unknown>)[k] = v
  }
  return o
}
const sameFields = (a: CardFields, b: CardFields) => JSON.stringify(pickFields(a)) === JSON.stringify(pickFields(b))

export function cardText(c: CardFields): string {
  const p: (string | null | undefined)[] = [c.category, c.title, c.body, c.cta, ...(c.items ?? [])]
  if (c.left) p.push(`${c.left.label}: ${c.left.value}`)
  if (c.right) p.push(`${c.right.label}: ${c.right.value}`)
  return p.filter(Boolean).join('\n')
}

/** 숫자 규칙: 근거 원문에 없는 숫자가 카드에 있으면 bad. (backend/ai/verification/consistency/numbers.py 와 같은 취지) */
function numberRule(card: Card, source: string): CheckResult {
  const src = source.replace(/,/g, '')
  const nums = (cardText(card).match(/\d+(?:[.,]\d+)*/g) ?? []).filter((x) => !src.includes(x.replace(/,/g, '')))
  if (nums.length)
    return {
      card_id: card.card_id,
      verdict: 'bad',
      summary: '원문에 없는 숫자가 들어갔어요.',
      issues: nums.map((x) => ({ type: '수치 변경', source_span: '', card_span: x, explanation: `‘${x}’은 근거 원문에 없는 숫자예요.` })),
      by: 'rule',
    }
  return {
    card_id: card.card_id,
    verdict: 'warn',
    summary: '숫자·날짜는 원문과 같아요. 조건과 서술어가 원문과 같은지 확인해 주세요.',
    issues: [],
    by: 'rule',
  }
}

export function createMockApi(): CardSyncApi {
  const docs = new Map<string, State>()
  const jobs = new Map<string, Job>()

  function state(id: string): State {
    const s = docs.get(id)
    if (!s) throw new ApiError(404, '존재하지 않는 문서입니다.')
    return s
  }

  function startJob(kind: Job['kind'], documentId: string, ms: number, done: () => void): StartedJob {
    const job: Job = { job_id: `job-${Math.random().toString(36).slice(2, 8)}`, kind, status: 'running', stage: STAGES[kind][0], document_id: documentId, error: null, elapsed_seconds: null }
    jobs.set(job.job_id, job)
    const started = Date.now()
    STAGES[kind].forEach((st, i) => setTimeout(() => (job.stage = st), (ms / STAGES[kind].length) * i))
    setTimeout(() => {
      done()
      job.status = 'succeeded'
      job.elapsed_seconds = (Date.now() - started) / 1000
    }, ms)
    return { document_id: documentId, job_id: job.job_id }
  }

  const sourceOf = (s: State, c: Card) => {
    const m = new Map(s.document.sentences.map((x) => [x.sentence_id, x.text]))
    return c.sids.map((id) => m.get(id)).filter(Boolean).join(' ')
  }

  function resolveCheck(s: State, c: Card): CheckResult {
    const original = s.sample.cards.find((x) => x.card_id === c.card_id)
    if (original && sameFields(c, original)) return { ...s.sample.checks[c.card_id], card_id: c.card_id }
    if (c.repair && sameFields(c, { ...c, ...c.repair.fields })) return { ...c.repair.check, lint: c.repair.lint ?? [] }
    return numberRule(c, sourceOf(s, c))
  }

  return {
    mode: 'mock',
    health: async () => ({ status: 'mock', openai_key_configured: false }),
    sources: async (): Promise<SourceOption[]> =>
      SAMPLES.map((s) => ({ key: s.key, title: s.document.source.title ?? '', url: s.document.source.source_url ?? '', date: s.document.source.date ?? '', sentence_count: s.document.sentences.length })),
    sourceText: async (key) => {
      const s = SAMPLES.find((x) => x.key === key)
      if (!s) return null
      return { text: s.document.sentences.map((x) => x.text).join('\n'), title: s.document.source.title, source_url: s.document.source.source_url, source_name: s.document.source.source_name, license: s.document.source.license }
    },
    createDocument: async (body: DocumentIn) => {
      const text = body.text.trim()
      if (!text) throw new ApiError(400, '원문이 비어 있습니다.')
      const sample = SAMPLES.find((s) => body.source_url === s.document.source.source_url || s.document.sentences.some((x) => text.includes(x.text)))
      if (!sample) throw new ApiError(422, '이 주소의 원문을 불러오지 못했어요. 최근 정책브리핑 목록에서 선택해 주세요.')
      const id = `${sample.document.document_id}-${docs.size + 1}`
      const st: State = { sample, document: { ...clone(sample.document), document_id: id, status: 'analyzing' }, cards: [], selectionVersion: 0, cardsSelectionVersion: null }
      docs.set(id, st)
      return startJob('analysis', id, DELAY.analysis, () => (st.document.status = 'analyzed'))
    },
    getJob: async (jobId) => {
      const j = jobs.get(jobId)
      if (!j) throw new ApiError(404, '존재하지 않는 작업입니다.')
      return { ...j }
    },
    getDocument: async (id) => {
      const s = state(id)
      if (s.document.status === 'analyzing') throw new ApiError(409, '아직 분석 중인 문서입니다.')
      return clone(s.document)
    },
    putSelection: async (id, groupIds) => {
      const s = state(id)
      if (!groupIds.length) throw new ApiError(400, '선택된 그룹이 없습니다.')
      const ordered = s.document.groups.map((g) => g.group_id).filter((g) => groupIds.includes(g))
      if (JSON.stringify(ordered) !== JSON.stringify(s.document.required_group_ids)) s.selectionVersion++
      s.document.required_group_ids = ordered
      return { cards_outdated: s.cards.length > 0 && s.cardsSelectionVersion !== s.selectionVersion }
    },
    createCards: async (id, overwrite) => {
      const s = state(id)
      if (!s.document.required_group_ids.length) throw new ApiError(400, '선택된 그룹이 없습니다.')
      if (s.cards.length && !overwrite) throw new ApiError(409, '이미 만든 카드가 있습니다.')
      const sel = new Set(s.document.groups.filter((g) => s.document.required_group_ids.includes(g.group_id)).flatMap((g) => g.sentence_ids))
      return startJob('generation', id, DELAY.generation, () => {
        s.cards = clone(s.sample.cards)
          .filter((c) => c.group_id === null || c.sids.some((x) => sel.has(x)))
          .map((c, i) => ({ ...c, order: i + 1 }))
        s.cardsSelectionVersion = s.selectionVersion
        s.document.status = 'generated'
      })
    },
    listCards: async (id) => clone(state(id).cards),
    patchCard: async (id, cardId, expectedVersion, fields: Partial<CardFields>) => {
      const s = state(id)
      const c = s.cards.find((x) => x.card_id === cardId)
      if (!c) throw new ApiError(404, '존재하지 않는 카드입니다.')
      if (c.version !== expectedVersion) throw new ApiError(409, '다른 곳에서 먼저 수정했습니다. 새로 고친 뒤 다시 시도하세요.')
      const next = { ...c, ...fields }
      if (sameFields(next, c)) return clone(c)
      Object.assign(c, fields, { version: c.version + 1, status: 'pending' as const })
      return clone(c)
    },
    createChecks: async (id, cardIds) => {
      const s = state(id)
      const targets = s.cards.filter((c) => c.sids.length && (cardIds ? cardIds.includes(c.card_id) : c.status === 'unchecked' || c.status === 'pending'))
      if (!targets.length) throw new ApiError(409, '검사할 카드가 없습니다.')
      const versions = new Map(targets.map((c) => [c.card_id, c.version]))
      const job = startJob('check', id, DELAY.check, () => {
        for (const c of targets) {
          if (c.version !== versions.get(c.card_id)) continue
          const check = { ...resolveCheck(s, c), card_version: c.version }
          c.check = check
          c.status = check.verdict
        }
      })
      return { job_id: job.job_id, card_ids: targets.map((c) => c.card_id) }
    },
    record: async (id): Promise<ExportRecord> => {
      const s = state(id)
      const selected = new Set(s.document.required_group_ids)
      return {
        exported_at: new Date().toISOString(),
        document_id: id,
        source: s.document.source,
        sentences: s.document.sentences,
        groups: s.document.groups.map((g) => ({ ...g, selected: selected.has(g.group_id) })),
        cards: clone(s.cards),
        unverified_card_count: s.cards.filter((c) => c.status !== 'ok').length,
      }
    },
  }
}
