import { useState } from 'react'
import Head from '../components/common/Head'
import type { Workflow } from '../hooks/useWorkflow'
import { COLORS } from '../lib/colors'


export default function GroupsView({ wf }: { wf: Workflow }) {
  const doc = wf.document!
  const [focus, setFocus] = useState<string | null>(null)
  const groupIndex = (sid: string) => doc.groups.findIndex((g) => g.sentence_ids.includes(sid))
  const chosen = doc.groups.filter((g) => wf.selected.has(g.group_id))
  const count = chosen.length ? `${chosen.length}개 묶음 · 문장 ${chosen.reduce((a, g) => a + g.sentence_ids.length, 0)}개` : '선택 없음 · 묶음을 하나 이상 골라 주세요'

  return (
    <>
      <Head title="꼭 담을 내용을 골라 주세요." lead="형광펜이 칠해진 문장이 카드에 들어가요. 문장을 누르면 그 묶음을 넣고 뺄 수 있어요." />
      <div className="pick2">
        <div className="paper">
          <div className="row between">
            <b>{doc.source.title}</b>
            {doc.source.source_url ? (
              <a className="small" href={doc.source.source_url} target="_blank" rel="noopener">
                원문 보기 ↗
              </a>
            ) : null}
          </div>
          <p className={`src2 ${focus ? 'focus' : ''}`} id="src2">
            {doc.sentences.map((t) => {
              const gi = groupIndex(t.sentence_id)
              const g = doc.groups[gi]
              if (!g)
                return (
                  <span key={t.sentence_id} className="hl2 off">
                    <sup>{t.sentence_id.slice(1)}</sup>
                    {t.text}
                  </span>
                )
              const col = COLORS[gi % COLORS.length]
              const cls = ['hl2', wf.selected.has(g.group_id) ? '' : 'off', focus === g.group_id ? 'on' : ''].join(' ')
              return (
                <span key={t.sentence_id} className={cls} style={{ ['--tint' as string]: col[0], ['--d' as string]: col[1] }} onClick={() => wf.toggleGroup(g.group_id)}>
                  <sup>{t.sentence_id.slice(1)}</sup>
                  {t.text}{' '}
                </span>
              )
            })}
          </p>
        </div>
        <aside className="glist2">
          <div className="row between">
            <b id="selcount">{count}</b>
            <span className="row">
              <button className="quiet small" onClick={wf.selectAll}>
                모두 선택
              </button>
              <button className="quiet small" onClick={wf.selectNone}>
                해제
              </button>
            </span>
          </div>
          {doc.groups.map((g, gi) => {
            const col = COLORS[gi % COLORS.length]
            const on = wf.selected.has(g.group_id)
            return (
              <label key={g.group_id} className={`g2 ${on ? 'on' : ''}`} style={{ ['--tint' as string]: col[0], ['--d' as string]: col[1] }} onMouseEnter={() => setFocus(g.group_id)} onMouseLeave={() => setFocus(null)}>
                <input type="checkbox" checked={on} onChange={() => wf.toggleGroup(g.group_id)} />
                <span className="sw" />
                <span>
                  <b>{g.topic || g.headline}</b>
                  <small>
                    문장 {g.sentence_ids.length}개
                    {g.summary_check?.fallback ? ' · 요약 대신 원문 문장을 그대로 썼어요' : g.summary_check?.retried ? ' · 요약을 한 번 다시 만들었어요' : ''}
                  </small>
                  {g.summary_check?.fallback && g.summary_check.reason ? (
                    <small className="error">{g.summary_check.reason}</small>
                  ) : null}
                </span>
              </label>
            )
          })}
        </aside>
      </div>
      {wf.error ? (
        <p className="error" role="alert">
          {wf.error}
        </p>
      ) : null}
      <div className="bar">
        <button onClick={() => wf.go(0)}>← 원문 입력</button>
        <button className="primary" onClick={wf.generate}>
          선택한 정보로 카드 만들기 →
        </button>
      </div>
    </>
  )
}
