import { useEffect } from 'react'
import CardFrame from '../components/card/CardFrame'
import Head from '../components/common/Head'
import Marks from '../components/common/Marks'
import StatusPill from '../components/common/StatusPill'
import { cardText } from '../api/mock'
import type { Workflow } from '../hooks/useWorkflow'
import { LAYOUT_NAME, type Card, type CardFields } from '../types/domain'

const pick = (c: CardFields) => JSON.stringify([c.category, c.title, c.body, c.cta, c.items, c.left, c.right].map((v) => v ?? null))

function Row({ card, i, n, wf }: { card: Card; i: number; n: number; wf: Workflow }) {
  const v = card.status
  const ck = card.check
  const live = (v === 'ok' || v === 'warn' || v === 'bad') && ck
  const issues = live ? ck.issues : []
  const key = (j: number) => `${i}-${j}`
  const m = new Map(wf.document?.sentences.map((s) => [s.sentence_id, s.text]))
  const source = card.sids.map((id) => m.get(id)).filter(Boolean).join(' ')
  const canRepair = (v === 'warn' || v === 'bad') && !!card.repair && pick({ ...card, ...card.repair.fields }) !== pick(card)
  return (
    <article className={`a4 v-${v}`}>
      <button className="a4-mini" onClick={() => (wf.setCurrent(i), wf.go(2))} aria-label={`카드 ${i + 1} 편집`}>
        <CardFrame card={card} index={i} total={n} width={150} />
      </button>
      <div>
        <header>
          <StatusPill status={v} />
          <b>
            카드 {i + 1} · {LAYOUT_NAME[card.layout_id]}
          </b>
          <small>근거 {card.sids.join(' ')}</small>
        </header>
        <div className="pair">
          <div>
            <small>근거 원문</small>
            <p>
              <Marks text={source} spans={issues.map((x, j) => ({ text: x.source_span, cls: 'miss', key: key(j) }))} />
            </p>
          </div>
          <div className="arrow">→</div>
          <div>
            <small>카드 문구</small>
            <p className="pre">
              <Marks text={cardText(card)} spans={issues.map((x, j) => ({ text: x.card_span, cls: 'chg', key: key(j) }))} />
            </p>
          </div>
        </div>
        {v === 'unchecked' ? (
          <p className="note">아직 검사하지 않았어요.</p>
        ) : v === 'pending' ? (
          <p className="note">문구가 바뀌어 이전 판정은 만료됐어요. 다시 검사해 주세요.</p>
        ) : issues.length ? (
          <ol className="notes">
            {issues.map((x, j) => (
              <li key={j} data-k={key(j)}>
                <b>{x.type}</b>
                {x.explanation}
              </li>
            ))}
          </ol>
        ) : (
          <p className="note">{ck?.summary ?? ''}</p>
        )}
        {live && ck.lint?.length ? <p className="note warntext">글자 수 한도를 넘었어요 · {ck.lint.map((x) => x.replace(/^C\d+\./, '')).join(', ')}</p> : null}
        {live && ck.by ? <p className="note small muted">판정: {ck.by === 'rule' ? '숫자 규칙' : 'LLM'}{ck.checker ? ` · ${ck.checker}` : ''}</p> : null}
        <div className="acts">
          {canRepair ? (
            <button className="primary" onClick={() => wf.applyRepair(card.card_id)}>
              AI 수정안 적용
            </button>
          ) : null}
          {v === 'warn' || v === 'bad' ? <button onClick={() => (wf.setCurrent(i), wf.go(2))}>직접 수정</button> : null}
        </div>
      </div>
    </article>
  )
}

export default function CheckView({ wf }: { wf: Workflow }) {
  const cs = wf.cards
  const n = cs.length
  const prob = cs.filter((c) => c.status === 'warn' || c.status === 'bad').length
  const pend = cs.filter((c) => c.status === 'pending' || c.status === 'unchecked').length
  const unc = cs.filter((c) => c.status === 'unchecked').length
  const t = wf.checkFailed ? '검사를 완료하지 못했어요.' : prob ? `카드 ${n}장 중 ${prob}장이 원문과 달라졌어요.` : pend ? (unc === pend ? `아직 검사하지 않은 카드가 ${pend}장 있어요.` : `고친 카드 ${pend}장을 다시 검사해 주세요.`) : '모든 카드가 원문과 일치해요.'
  const p = wf.checkFailed ? '잠시 후 다시 시도해 주세요. 이전 결과는 새 검사 결과로 쓰지 않아요.' : '빨간 바탕은 원문에서 빠지거나 바뀐 부분, 물결 밑줄은 카드에서 달라진 표현이에요. 표시를 가리키면 짝이 함께 강조돼요.'

  // 같은 data-k 끼리 hover 강조
  useEffect(() => {
    const h = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      const a = target.closest('.a4')
      document.querySelectorAll('.a4 .hl').forEach((x) => x.classList.remove('hl'))
      const t = target.closest<HTMLElement>('[data-k]')
      if (a && t) a.querySelectorAll(`[data-k="${t.dataset.k}"]`).forEach((x) => x.classList.add('hl'))
    }
    document.addEventListener('mouseover', h)
    return () => document.removeEventListener('mouseover', h)
  }, [])

  return (
    <>
      <Head title={t} lead={p} />
      {wf.checkFailed || wf.error ? (
        <div className="paper">
          <div className="notice warn" role="alert">
            {wf.error ?? '검사 서버의 응답이 없어 판정을 받지 못했어요.'}
          </div>
          <button className="primary" onClick={() => wf.inspect()}>
            다시 검사하기
          </button>
        </div>
      ) : (
        <div className="paper">
          {cs.map((c, i) => (
            <Row key={c.card_id} card={c} i={i} n={n} wf={wf} />
          ))}
        </div>
      )}
      <div className="bar">
        <button onClick={() => wf.go(2)}>← 카드 편집</button>
        <div className="row">
          <button disabled={!pend && !wf.checkFailed} onClick={() => wf.inspect()}>
            고친 카드 다시 검사
          </button>
          <button className="primary" disabled={wf.checkFailed} onClick={() => wf.go(4)}>
            독자 미리보기 →
          </button>
        </div>
      </div>
    </>
  )
}
