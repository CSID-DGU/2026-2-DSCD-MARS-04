import { useEffect, useRef, useState } from 'react'
import CardFrame from '../components/card/CardFrame'
import { overflowed } from '../components/card/util'
import Head from '../components/common/Head'
import { STATUS } from '../components/common/status'
import type { Workflow } from '../hooks/useWorkflow'
import { LAYOUT_NAME, type Card, type CardFields } from '../types/domain'

const LIMITS: Partial<Record<Card['layout_id'], Partial<Record<'title' | 'category' | 'body' | 'cta', number>>>> = {
  cover: { title: 28, category: 10 },
  body: { title: 24, body: 110 },
  checklist: { title: 24 },
  steps: { title: 24 },
  compare: { title: 24 },
  closing: { title: 20, body: 60, cta: 20 },
}

function usePreviewWidth(max: number) {
  const [w, setW] = useState(max)
  useEffect(() => {
    const f = () => setW(Math.max(220, Math.min(max, (document.getElementById('app')?.clientWidth ?? 1000) - 40)))
    f()
    window.addEventListener('resize', f)
    return () => window.removeEventListener('resize', f)
  }, [max])
  return w
}

function Counter({ value, max }: { value: string; max?: number }) {
  if (!max) return null
  const n = value.replace(/\n/g, '').length
  return (
    <span className={`count ${n > max ? 'over' : ''}`}>
      {n}/{max}
    </span>
  )
}

function Field({ id, label, value, max, multi, onChange }: { id: string; label: string; value: string; max?: number; multi?: boolean; onChange: (v: string) => void }) {
  return (
    <>
      <label htmlFor={id}>
        {label} <Counter value={value} max={max} />
      </label>
      {multi ? <textarea id={id} rows={3} value={value} onChange={(e) => onChange(e.target.value)} /> : <input type="text" id={id} value={value} onChange={(e) => onChange(e.target.value)} />}
    </>
  )
}

function ImagePanel({ card, wf }: { card: Card; wf: Workflow }) {
  const im = card.image
  const src = wf.document?.source_images ?? []
  const onUpload = (f: File | undefined) => {
    if (!f) return
    const r = new FileReader()
    r.onload = () => wf.setCardImage(card.card_id, { stage: 'upload', data: String(r.result), ...(im?.stage === 'unsplash' ? { id: im.id, author: im.author, author_url: im.author_url, photo_url: im.photo_url, query: im.query } : {}) })
    r.readAsDataURL(f)
  }
  return (
    <div className="imgstage">
      <div className="stage-row">
        <b>① 원문 이미지</b>
        {src.length ? (
          <div className="srcimgs">
            {src.map((x) => (
              <figure key={x.url}>
                <img src={x.url} alt="" loading="lazy" onError={(e) => e.currentTarget.parentElement?.classList.add('broken')} />
                <figcaption>사용 불가 · 저작권자 허락 필요</figcaption>
              </figure>
            ))}
          </div>
        ) : (
          <small>원문에 쓸 수 있는 이미지가 없어요.</small>
        )}
      </div>
      <div className="stage-row">
        <b>② Unsplash</b>
        {im?.stage === 'unsplash' ? (
          <div className="pick">
            <img src={im.data} alt={im.alt ?? ''} />
            <div>
              <small>검색어 ‘{im.query ?? card.image_query}’</small>
              <br />
              <a href={im.photo_url} target="_blank" rel="noopener">
                사진: {im.author} / Unsplash ↗
              </a>
            </div>
          </div>
        ) : im?.stage === 'upload' ? (
          <small>직접 올린 이미지를 쓰고 있어요.</small>
        ) : (
          <small>{im?.message ?? '맞는 이미지를 찾지 못했어요. 이미지를 직접 올려 주세요.'}</small>
        )}
      </div>
      <div className="stage-row">
        <b>③ 직접 올리기</b>
        <div className="row">
          <label className="upload">
            <input type="file" accept="image/*" onChange={(e) => onUpload(e.target.files?.[0])} />
            이미지 선택
          </label>
        </div>
      </div>
    </div>
  )
}

/** 카드가 바뀌면 draft 를 새로 만들도록 key 로 다시 마운트한다 */
export default function EditView({ wf }: { wf: Workflow }) {
  const card = wf.cards[wf.current]
  return <EditCard key={card.card_id} wf={wf} />
}

function EditCard({ wf }: { wf: Workflow }) {
  const n = wf.cards.length
  const card = wf.cards[wf.current]
  const W = usePreviewWidth(460)
  const liveRef = useRef<HTMLDivElement>(null)
  const [draft, setDraft] = useState<CardFields>(() => ({ ...card }))
  const [over, setOver] = useState(false)
  const timer = useRef<number | null>(null)
  const sentences = new Map(wf.document?.sentences.map((s) => [s.sentence_id, s.text]))

  useEffect(() => {
    // 렌더 후 DOM 크기로 넘침을 판단한다 (외부 시스템: 레이아웃)
    const id = requestAnimationFrame(() => setOver(overflowed(liveRef.current)))
    return () => cancelAnimationFrame(id)
  }, [draft])

  const change = (patch: Partial<CardFields>) => {
    const next = { ...draft, ...patch }
    setDraft(next)
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => wf.editCard(card.card_id, patch), 500)
  }
  const preview: Card = { ...card, ...draft }
  const L = LIMITS[card.layout_id] ?? {}

  return (
    <>
      <Head title="카드에서 직접 다듬으세요." lead="문구를 고치면 이전 검사 결과는 만료돼요. 근거 문장과 이미지 출처는 오른쪽에서 확인할 수 있어요." />
      <div className="strip">
        {wf.cards.map((x, i) => (
          <button key={x.card_id} className={`thumb2 ${i === wf.current ? 'active' : ''}`} onClick={() => wf.setCurrent(i)} aria-label={`카드 ${i + 1}`}>
            <CardFrame card={i === wf.current ? preview : x} index={i} total={n} width={92} />
            <span className="small">
              <i className="dot" style={{ background: STATUS[x.status].color }} />
              {i + 1} {LAYOUT_NAME[x.layout_id]}
            </span>
          </button>
        ))}
      </div>
      <div className="grid">
        <div>
          <div id="livecard">
            <CardFrame ref={liveRef} card={preview} index={wf.current} total={n} width={W} />
          </div>
          <p className="error small" role="status">
            {over ? '글자가 카드 영역을 넘쳐요. 문구를 줄여 주세요.' : ''}
          </p>
        </div>
        <div className="paper">
          <div className="row between">
            <span className="code">
              {LAYOUT_NAME[card.layout_id]} · 근거 {card.sids.join(' ')}
            </span>
            <span className="status">{STATUS[card.status].label}</span>
          </div>
          {card.layout_id === 'cover' ? <Field id="f-category" label="카테고리" value={draft.category ?? ''} max={L.category} onChange={(v) => change({ category: v })} /> : null}
          <Field id="f-title" label="제목" value={draft.title} max={L.title} multi={card.layout_id === 'cover'} onChange={(v) => change({ title: v })} />
          {card.layout_id === 'body' || card.layout_id === 'closing' ? <Field id="f-body" label="본문" value={draft.body ?? ''} max={L.body} multi onChange={(v) => change({ body: v })} /> : null}
          {card.layout_id === 'closing' ? <Field id="f-cta" label="행동 유도" value={draft.cta ?? ''} max={L.cta} onChange={(v) => change({ cta: v })} /> : null}
          {card.layout_id === 'checklist' || card.layout_id === 'steps' ? (
            <Field id="f-items" label="항목 · 한 줄에 하나씩, 2~6개" value={(draft.items ?? []).join('\n')} multi onChange={(v) => change({ items: v.split('\n').map((x) => x.trim()).filter(Boolean) })} />
          ) : null}
          {card.layout_id === 'compare' ? (
            <div className="two-in">
              <Field id="f-ll" label="왼쪽 이름" value={draft.left?.label ?? ''} onChange={(v) => change({ left: { label: v, value: draft.left?.value ?? '' } })} />
              <Field id="f-rl" label="오른쪽 이름" value={draft.right?.label ?? ''} onChange={(v) => change({ right: { label: v, value: draft.right?.value ?? '' } })} />
              <Field id="f-lv" label="왼쪽 내용" value={draft.left?.value ?? ''} onChange={(v) => change({ left: { label: draft.left?.label ?? '', value: v } })} />
              <Field id="f-rv" label="오른쪽 내용" value={draft.right?.value ?? ''} onChange={(v) => change({ right: { label: draft.right?.label ?? '', value: v } })} />
            </div>
          ) : null}
          {wf.error ? (
            <p className="error small" role="alert">
              {wf.error}
            </p>
          ) : null}
          <details>
            <summary>근거 문장 {card.sids.length}개</summary>
            {card.sids.map((id) => (
              <blockquote key={id}>
                <sup>{id}</sup> {sentences.get(id)}
              </blockquote>
            ))}
          </details>
          <h3 className="sub">카드 이미지</h3>
          <ImagePanel card={card} wf={wf} />
        </div>
      </div>
      <div className="bar">
        <button onClick={() => wf.go(1)}>← 정보 다시 선택</button>
        <button className="primary" onClick={() => wf.inspect()}>
          전체 카드 검사 →
        </button>
      </div>
    </>
  )
}
