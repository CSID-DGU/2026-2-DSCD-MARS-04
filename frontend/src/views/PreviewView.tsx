import { useEffect } from 'react'
import CardFrame from '../components/card/CardFrame'
import Head from '../components/common/Head'
import { sourceLabel } from '../components/card/util'
import type { Workflow } from '../hooks/useWorkflow'

export default function PreviewView({ wf }: { wf: Workflow }) {
  const n = wf.cards.length
  const c = wf.cards[wf.reader]
  const s = wf.document!.source
  const W = Math.max(220, Math.min(520, (document.getElementById('app')?.clientWidth ?? 1000) - 40))
  const photos = [...new Map(wf.cards.filter((x) => x.image?.stage === 'unsplash').map((x) => [x.image!.id, x.image!])).values()]

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' && wf.reader < n - 1) wf.setReader(wf.reader + 1)
      if (e.key === 'ArrowLeft' && wf.reader > 0) wf.setReader(wf.reader - 1)
    }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [wf, n])

  return (
    <>
      <Head title="독자에게는 이렇게 보여요." lead="편집 도구를 내려놓고 순서대로 넘겨 보세요." />
      <div className="reader2">
        <div className="readercard">
          <CardFrame card={c} index={wf.reader} total={n} width={W} />
        </div>
        <div className="bar">
          <button disabled={!wf.reader} onClick={() => wf.setReader(wf.reader - 1)}>
            ← 이전
          </button>
          <span className="dots">
            {wf.cards.map((x, i) => (
              <i key={x.card_id} className={i === wf.reader ? 'on' : ''} />
            ))}
          </span>
          <button disabled={wf.reader === n - 1} onClick={() => wf.setReader(wf.reader + 1)}>
            다음 →
          </button>
        </div>
        <div className="caption">
          <b>게시 글에 함께 넣을 출처</b>
          <p>
            출처: {sourceLabel(s)} 「{s.title}」{s.date ? `(${s.date})` : ''} · {s.license ?? ''}
          </p>
          <p>
            {photos.map((p, i) => (
              <span key={p.id ?? i}>
                {i ? ' · ' : ''}사진:{' '}
                <a href={p.author_url} target="_blank" rel="noopener">
                  {p.author}
                </a>{' '}
                /{' '}
                <a href="https://unsplash.com/?utm_source=cardsync&utm_medium=referral" target="_blank" rel="noopener">
                  Unsplash
                </a>
              </span>
            ))}
          </p>
        </div>
      </div>
      <div className="bar">
        <button onClick={() => (wf.setCurrent(wf.reader), wf.go(2))}>다시 편집</button>
        <button className="primary" onClick={() => wf.go(5)}>
          내보내기 →
        </button>
      </div>
    </>
  )
}
