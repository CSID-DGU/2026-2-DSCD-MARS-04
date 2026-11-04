import { useState } from 'react'
import Head from '../components/common/Head'
import type { Workflow } from '../hooks/useWorkflow'

export default function InputView({ wf }: { wf: Workflow }) {
  const [url, setUrl] = useState(wf.document?.source.source_url ?? '')
  const [text, setText] = useState('')
  const [picked, setPicked] = useState<string | null>(null)
  const [err, setErr] = useState('')
  const mock = wf.mode === 'mock'

  const pick = async (key: string) => {
    const s = wf.sources.find((x) => x.key === key)
    if (!s) return
    setPicked(key)
    setUrl(s.url)
    setErr('')
    const body = await wf.pickSource(key)
    if (body) setText(body.text)
  }

  const submit = async () => {
    const u = url.trim()
    const t = text.trim()
    if (mock) {
      if (!u && !t) return setErr('원문 주소를 입력하거나 목록에서 선택해 주세요.')
      const s = wf.sources.find((x) => u === x.url || (u && x.url.includes(u.split('newsId=')[1] ?? '\u0000')))
      if (!s && !t) return setErr('이 주소의 원문을 불러오지 못했어요. 최근 정책브리핑 목록에서 선택해 주세요.')
      const body = s ? await wf.pickSource(s.key) : null
      await wf.analyze(body ?? { text: t, source_url: u || null })
      return
    }
    if (!t) return setErr('원문 본문을 붙여넣어 주세요. (URL 자동 수집은 아직 없어요)')
    await wf.analyze({ text: t, source_url: u || null, source_name: u.includes('korea.kr') ? '대한민국 정책브리핑' : null })
  }

  return (
    <>
      <Head title="어떤 이야기를 전할까요?" lead="기사나 보도자료 본문을 넣으면 원문을 문장 단위로 나눠 근거로 보관해요." />
      <div className="grid">
        <div className="paper">
          <label htmlFor="url">원문 주소</label>
          <div className="row nowrap">
            <input type="url" id="url" placeholder="https://www.korea.kr/news/..." value={url} onChange={(e) => setUrl(e.target.value)} />
            <button className="primary" id="analyze" onClick={submit}>
              불러오기
            </button>
          </div>
          <label htmlFor="text" style={{ marginTop: 12 }}>
            원문 본문
          </label>
          <textarea id="text" rows={mock ? 4 : 10} value={text} onChange={(e) => setText(e.target.value)} placeholder="본문을 붙여넣어 주세요." />
          <p className="error" id="inputerror" role="alert">
            {err || wf.error || ''}
          </p>
          {wf.sources.length ? (
            <>
              <h3 className="sub">최근 정책브리핑</h3>
              <div className="srclist">
                {wf.sources.map((s) => (
                  <button key={s.key} className={`srcrow ${picked === s.key ? 'on' : ''}`} onClick={() => pick(s.key)}>
                    <b>{s.title}</b>
                    <small>
                      {s.date} · 대한민국 정책브리핑 · 문장 {s.sentence_count}개
                    </small>
                  </button>
                ))}
              </div>
            </>
          ) : null}
        </div>
        <aside>
          <h2>
            원문은 남기고,
            <br />
            전할 내용만 고릅니다.
          </h2>
          <p className="muted">카드를 고쳐도 근거 문장은 사라지지 않아요. 문구가 바뀌면 검사 상태도 함께 바뀝니다.</p>
          <p className="muted small">본문 텍스트는 공공누리 제1유형(출처 표시) 조건에 따라 쓰고, 모든 카드에 출처를 표기해요.</p>
          {wf.fallback ? <p className="muted small">백엔드에 연결하지 못해 샘플 데이터로 동작 중이에요.</p> : null}
        </aside>
      </div>
    </>
  )
}
