/** 데모 샘플(JSON)을 백엔드와 같은 Document / Card 모양으로 바꾼다. */
import raw from './samples.json'
import type { Card, CardFields, CheckResult, Document, LayoutId, Repair, SourceImage } from '../types/domain'

interface RawSample {
  key: string
  source: { url: string; title: string; date: string; license: string }
  sourceImages?: SourceImage[]
  sentences: { id: string; text: string }[]
  groups: { id: string; title: string; sids: string[] }[]
  cards: (CardFields & {
    id: string
    layout: LayoutId
    sids: string[]
    image_query: string
    image?: Card['image']
    repair?: Repair
  })[]
  checks: Record<string, CheckResult>
}

export interface Sample {
  key: string
  document: Document
  /** 생성 직후 상태의 카드(검사 전) */
  cards: Card[]
  /** 생성 직후 카드에 대한 저장된 검사 결과 */
  checks: Record<string, CheckResult>
}

function groupOf(sample: RawSample, sids: string[]): string | null {
  const g = sample.groups.find((x) => sids.some((s) => x.sids.includes(s)))
  return g ? g.id : null
}

export const SAMPLES: Sample[] = (raw as RawSample[]).map((s) => {
  const document: Document = {
    document_id: `sample-${s.key}`,
    status: 'analyzed',
    source: {
      title: s.source.title,
      source_url: s.source.url,
      source_name: '대한민국 정책브리핑',
      license: s.source.license,
      date: s.source.date,
    },
    sentences: s.sentences.map((t) => ({ sentence_id: t.id, text: t.text })),
    groups: s.groups.map((g) => ({
      group_id: g.id,
      sentence_ids: g.sids,
      summary: '',
      topic: g.title,
      headline: g.title,
    })),
    required_group_ids: s.groups.map((g) => g.id),
    source_images: s.sourceImages ?? [],
  }
  const cards: Card[] = s.cards.map((c, i) => ({
    card_id: c.id,
    layout_id: c.layout,
    group_id: c.layout === 'cover' || c.layout === 'closing' ? null : groupOf(s, c.sids),
    sids: c.sids,
    image_query: c.image_query,
    title: c.title,
    category: c.category ?? null,
    body: c.body ?? null,
    items: c.items ?? null,
    left: c.left ?? null,
    right: c.right ?? null,
    cta: c.cta ?? null,
    order: i + 1,
    version: 1,
    status: 'unchecked',
    check: null,
    image: c.image,
    repair: c.repair ?? null,
  }))
  return { key: s.key, document, cards, checks: s.checks }
})
