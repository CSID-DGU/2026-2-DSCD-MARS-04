import { useEffect, useState } from 'react'
import type { BusyKind } from '../../hooks/useWorkflow'

const LOAD: Record<BusyKind, { title: string; steps: string[] }> = {
  analysis: { title: '원문을 불러와 정보 묶음을 나누고 있어요.', steps: ['원문 불러오기', '문장 나누기', '정보 묶음 정리'] },
  generation: { title: '선택한 정보로 카드뉴스를 만들고 있어요.', steps: ['카피 작성 · 렌더 스펙', '① 원문 이미지 확인', '② Unsplash 이미지 검색', '레이아웃 적용'] },
  check: { title: '카드 문구와 근거 원문을 대조하고 있어요.', steps: ['문장별 근거 연결', '조건·수치·서술어 대조', '판정 정리'] },
}

export default function Loading({ kind, stage }: { kind: BusyKind; stage: string | null }) {
  const { title, steps } = LOAD[kind]
  // 서버 stage 이름과 화면 단계는 1:1이 아니라서 시간으로 진행시키되, 끝나면 마지막 단계로
  const [k, setK] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setK((x) => Math.min(x + 1, steps.length - 1)), 1200)
    return () => clearInterval(t)
  }, [steps.length])
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
      {stage ? <p className="muted small">서버 단계: {stage}</p> : null}
      <div className="load-line" aria-hidden="true">
        <i />
      </div>
    </div>
  )
}
