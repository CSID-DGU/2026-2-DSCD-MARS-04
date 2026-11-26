import { useEffect, useState } from 'react'
import type { BusyKind } from '../../hooks/useWorkflow'

/**
 * 작업 대기 화면. 서버 진행 상황과 상관없이 시간 기준으로 일정하게 진행한다.
 * expected 는 11-05 실측(분석 30초, 생성 18초, 검사 24초)에 여유를 둔 값.
 * expected 까지 90%로 일정하게 가고, 넘으면 99%를 향해 점점 느리게 계속 간다(끝까지 멈추지 않음).
 */
const LOAD: Record<BusyKind, { title: string; steps: string[]; expected: number }> = {
  analysis: { title: '원문을 불러와 정보 묶음을 나누고 있어요.', steps: ['원문 불러오기', '문장 나누기', '정보 묶음 정리', '요약 확인'], expected: 35 },
  generation: { title: '선택한 정보로 카드뉴스를 만들고 있어요.', steps: ['카피 작성 · 렌더 스펙', '레이아웃 적용', '사진 찾기', '카드 정리'], expected: 25 },
  check: { title: '카드 문구와 근거 원문을 대조하고 있어요.', steps: ['문장별 근거 연결', '조건·수치·서술어 대조', '필수 정보 확인', '판정 정리'], expected: 30 },
}

const TICK_MS = 200

function progressAt(elapsed: number, expected: number): number {
  if (elapsed <= expected) return (elapsed / expected) * 0.9
  return 0.9 + 0.09 * (1 - Math.exp(-(elapsed - expected) / expected))
}

export default function Loading({ kind }: { kind: BusyKind; stage?: string | null }) {
  const { title, steps, expected } = LOAD[kind]
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = performance.now()
    const t = setInterval(() => setElapsed((performance.now() - started) / 1000), TICK_MS)
    return () => clearInterval(t)
  }, [kind])

  const p = progressAt(elapsed, expected)
  // 단계 표시도 같은 진행률로 고르게 넘어간다. 마지막 단계는 끝날 때까지 '진행 중'
  const k = Math.min(steps.length - 1, Math.floor((p / 0.9) * steps.length))
  const sec = Math.floor(elapsed)

  return (
    <div className="busy" role="status" aria-live="polite" aria-busy="true">
      <div className="orbit" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      <h2 className="load-title">{title}</h2>
      <div className="load-steps">
        {steps.map((s, i) => (
          <span key={s} className={i < k ? 'load-complete' : i === k ? 'now' : ''}>
            {s}
          </span>
        ))}
      </div>
      <div className="load-bar" aria-hidden="true">
        <i style={{ width: `${(p * 100).toFixed(1)}%` }} />
      </div>
      <p className="load-time">
        {sec}초 지남 · 보통 {expected - 10}~{expected}초 걸려요
        {elapsed > expected ? ' · 조금 더 걸리고 있어요' : ''}
      </p>
    </div>
  )
}
