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

