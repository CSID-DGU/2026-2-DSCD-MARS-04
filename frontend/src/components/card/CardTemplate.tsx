/**
 * 카드 템플릿: 렌더 스펙(Card) → 고정 레이아웃 6종.
 * 720×900 기준으로 그리고 CardFrame에서 scale로 줄인다.
 * (AX-Surfers card-news-plugin 템플릿을 참고해 손봄, MIT)
 */
import type { Card, CardImage } from '../../types/domain'
import { credit } from './util'
import '../../styles/card.css'

const LOGO = '/logo.svg'

function Svg({ d, size = 26, color = '#0866d9', width = 2 }: { d: string; size?: number; color?: string; width?: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  )
}

const ICON = {
  check: <Svg d="M5 12.5l4.5 4.5L19 7.5" size={16} color="#fff" width={3.2} />,
  heart: <Svg d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21.2l7.8-7.7 1-1.1a5.5 5.5 0 0 0 0-7.8z" />,
  comment: <Svg d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z" />,
  save: <Svg d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />,
}

function Bg({ image, className }: { image?: CardImage; className: string }) {
  return image?.data ? <img className={className} src={image.data} alt="" /> : <div className={`${className} cn-fallback`} />
}

function Meta({ card, index, total, sourceName }: { card: Card; index: number; total: number; sourceName?: string }) {
  return (
    <div className="cn-meta">
      <span>{credit(card.image, sourceName)}</span>
      <span>
        {index + 1} / {total}
      </span>
    </div>
  )
}

function Brand() {
  return (
    <div className="cn-brand">
      <img src={LOGO} alt="" />
      CardSync
    </div>
  )
}

export interface CardTemplateProps {
  card: Card
  /** 0부터 시작하는 순서 */
  index: number
  total: number
  sourceName?: string
}

export default function CardTemplate({ card, index, total, sourceName }: CardTemplateProps) {
  const meta = <Meta card={card} index={index} total={total} sourceName={sourceName} />
  switch (card.layout_id) {
    case 'cover':
      return (
        <div className="cn cn-cover">
          <Bg image={card.image} className="cn-bg" />
          <div className="cn-shade" />
          <Brand />
          <div className="cn-content">
            {card.category ? <span className="cn-badge">{card.category}</span> : null}
            <h1>{card.title}</h1>
          </div>
          {meta}
        </div>
      )
    case 'body':
      return (
        <div className="cn cn-body">
          <div className="cn-band">
            <Bg image={card.image} className="" />
          </div>
          <div className="cn-content">
            <div className="cn-num">{index}</div>
            <h2>{card.title}</h2>
            <div className="cn-bar" />
            <p>{card.body}</p>
          </div>
          {meta}
        </div>
      )
    case 'checklist':
    case 'steps': {
      const steps = card.layout_id === 'steps'
      return (
        <div className={`cn cn-light cn-${card.layout_id}`}>
          <div className="cn-band">
            <Bg image={card.image} className="" />
          </div>
          <div className="cn-content">
            <h2>{card.title}</h2>
            <ul className="cn-list">
              {(card.items ?? []).map((t, j) => (
                <li key={j}>
                  {steps ? <span className="cn-step">{j + 1}</span> : <span className="cn-check">{ICON.check}</span>}
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>
          {meta}
        </div>
      )
    }
    case 'compare': {
      const l = card.left ?? { label: '', value: '' }
      const r = card.right ?? { label: '', value: '' }
      return (
        <div className="cn cn-light cn-compare">
          <div className="cn-band">
            <Bg image={card.image} className="" />
          </div>
          <div className="cn-content">
            <h2>{card.title}</h2>
            <div className="cn-vs">
              <div className="cn-side cn-old">
                <small>{l.label}</small>
                <b>{l.value}</b>
              </div>
              <div className="cn-arrow">→</div>
              <div className="cn-side cn-new">
                <small>{r.label}</small>
                <b>{r.value}</b>
              </div>
            </div>
          </div>
          {meta}
        </div>
      )
    }
    default:
      return (
        <div className="cn cn-closing">
          <Bg image={card.image} className="cn-bg" />
          <div className="cn-tint" />
          <div className="cn-content">
            <Brand />
            <h2>{card.title}</h2>
            <div className="cn-bar" />
            <p>{card.body}</p>
            {card.cta ? <span className="cn-cta">{card.cta}</span> : null}
            <div className="cn-icons">
              {(['heart', 'comment', 'save'] as const).map((k) => (
                <span key={k} className="cn-icon">
                  {ICON[k]}
                </span>
              ))}
            </div>
          </div>
          {meta}
        </div>
      )
  }
}
