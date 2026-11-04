/** 720×900 카드를 width에 맞춰 scale로 줄여 보여주는 틀. */
import { forwardRef } from 'react'
import type { Card } from '../../types/domain'
import CardTemplate from './CardTemplate'

export interface CardFrameProps {
  card: Card
  index: number
  total: number
  width: number
  sourceName?: string
}

const CardFrame = forwardRef<HTMLDivElement, CardFrameProps>(function CardFrame({ card, index, total, width, sourceName }, ref) {
  return (
    <div ref={ref} className="cn-frame" style={{ width, height: width * 1.25 }}>
      <div className="cn-scale" style={{ transform: `scale(${width / 720})` }}>
        <CardTemplate card={card} index={index} total={total} sourceName={sourceName} />
      </div>
    </div>
  )
})

export default CardFrame

/** 카드 본문이 영역을 넘쳤는지(렌더된 DOM 기준) */
export function overflowed(root: HTMLElement | null): boolean {
  const el = root?.querySelector<HTMLElement>('.cn-content')
  return !!el && el.scrollHeight > el.clientHeight + 2
}
