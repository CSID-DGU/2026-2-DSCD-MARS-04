import { useState } from 'react'
import CardFrame from '../components/card/CardFrame'
import Head from '../components/common/Head'
import { STATUS } from '../components/common/status'
import type { Workflow } from '../hooks/useWorkflow'
import { cardToPngBlob, saveBlob } from '../lib/export'
import { sourceLabel } from '../components/card/util'
import { LAYOUT_NAME } from '../types/domain'

export default function DownloadView({ wf }: { wf: Workflow }) {
  const n = wf.cards.length
  const un = wf.cards.filter((c) => c.sids.length && c.status !== 'ok').length
  const [msg, setMsg] = useState('')
  const key = wf.document!.document_id
  const sourceName = sourceLabel(wf.document!.source)

  const png = async (i: number) => {
    const c = wf.cards[i]
    const blob = await cardToPngBlob(c, i, n, sourceName)
    saveBlob(blob, `CardSync-${key}-${String(i + 1).padStart(2, '0')}-v${c.version}.png`)
  }
  const one = async (i: number) => {
    try {
      await png(i)
      setMsg(`카드 ${i + 1} PNG를 저장했어요.`)
    } catch {
      setMsg('이미지를 만들지 못했어요. 다시 시도해 주세요.')
    }
  }
  const all = async () => {
    for (let i = 0; i < n; i++) {
      setMsg(`${i + 1}/${n}장 저장 중…`)
      try {
        await png(i)
      } catch {
        setMsg(`카드 ${i + 1} 저장에 실패했어요.`)
        return
      }
      await new Promise((r) => setTimeout(r, 250))
    }
    setMsg(`${n}장을 모두 저장했어요.`)
  }
  const report = async () => {
    try {
      const rec = await wf.record()
      saveBlob(new Blob([JSON.stringify(rec, null, 2)], { type: 'application/json' }), `CardSync-${key}-record.json`)
      setMsg('검수 기록을 저장했어요.')
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '기록을 만들지 못했어요.')
    }
  }

  return (
    <>
      <Head title="지금 확인한 버전을 저장해요." lead="카드 이미지(1080×1350 PNG)와, 원문·렌더 스펙·검사 결과가 연결된 기록을 내려받을 수 있어요." />
      <div className="grid">
        <div className="paper">
          <div className="row between">
            <h2>카드 이미지 · PNG</h2>
            <button onClick={all}>전체 저장</button>
          </div>
          {wf.cards.map((c, i) => (
            <div key={c.card_id} className="checkrow">
              <div className="row nowrap">
                <CardFrame card={c} index={i} total={n} width={64} />
                <div>
                  <b>
                    {i + 1}. {c.title.replace(/\n/g, ' ')}
                  </b>
                  <br />
                  <small>
                    {LAYOUT_NAME[c.layout_id]} · 문구 v{c.version} · {STATUS[c.status].label}
                  </small>
                </div>
              </div>
              <button onClick={() => one(i)}>PNG 저장</button>
            </div>
          ))}
          <p role="status">{msg}</p>
        </div>
        <div className="paper">
          <h2>검수 기록 · JSON</h2>
          <p>원문 문장, 선택한 정보 묶음, 카드 렌더 스펙, 검사 결과, 이미지 출처를 함께 저장해요.</p>
          <div className={`notice ${un ? 'warn' : ''}`}>{un ? `원문과 일치하지 않거나 검사하지 않은 카드가 ${un}장 있어요. 저장해도 문제가 해결되지는 않아요.` : '모든 카드가 검사를 통과했어요.'}</div>
          <button className="primary" onClick={report}>
            기록 다운로드
          </button>
        </div>
      </div>
      <div className="bar">
        <button onClick={() => wf.go(4)}>← 미리보기</button>
        <button
          onClick={() => {
            if (window.confirm('지금 작업을 끝내고 새 원문을 고를까요? 필요한 파일은 먼저 저장해 주세요.')) wf.reset()
          }}
        >
          새 원문으로 시작
        </button>
      </div>
    </>
  )
}
