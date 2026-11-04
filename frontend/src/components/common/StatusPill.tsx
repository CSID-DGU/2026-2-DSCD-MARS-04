import type { CardStatus } from '../../types/domain'
import { STATUS } from './status'


export default function StatusPill({ status }: { status: CardStatus }) {
  const v = STATUS[status]
  return (
    <span className="pill" style={{ color: v.color, background: v.bg }}>
      {v.label}
    </span>
  )
}
