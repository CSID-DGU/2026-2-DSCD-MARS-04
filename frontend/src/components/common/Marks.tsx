/** 본문 안에서 지정한 구간을 <mark>로 표시한다. 겹치는 구간은 앞의 것만 쓴다. */
import { Fragment } from 'react'

export interface Span {
  text: string
  cls: 'miss' | 'chg'
  key: string
}

export default function Marks({ text, spans }: { text: string; spans: Span[] }) {
  const found = spans
    .filter((s) => s.text)
    .map((s) => ({ ...s, start: text.indexOf(s.text) }))
    .filter((s) => s.start >= 0)
    .sort((a, b) => a.start - b.start)
  const out: React.ReactNode[] = []
  let pos = 0
  for (const s of found) {
    if (s.start < pos) continue
    out.push(<Fragment key={`t${pos}`}>{text.slice(pos, s.start)}</Fragment>)
    out.push(
      <mark key={s.key + s.start} className={s.cls} data-k={s.key}>
        {s.text}
      </mark>,
    )
    pos = s.start + s.text.length
  }
  out.push(<Fragment key="tail">{text.slice(pos)}</Fragment>)
  return <>{out}</>
}
