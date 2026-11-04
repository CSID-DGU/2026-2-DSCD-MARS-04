import type { CardImage } from '../../types/domain'

export function credit(image: CardImage | undefined, sourceName = '대한민국 정책브리핑'): string {
  const base = `출처 ${sourceName}`
  if (!image) return base
  if (image.stage === 'unsplash') return `${base} · 사진 ${image.author ?? ''} / Unsplash`
  if (image.stage === 'upload') return `${base} · 사진 직접 업로드`
  return base
}

/** 카드 본문이 영역을 넘쳤는지(렌더된 DOM 기준) */
export function overflowed(root: HTMLElement | null): boolean {
  const el = root?.querySelector<HTMLElement>('.cn-content')
  return !!el && el.scrollHeight > el.clientHeight + 2
}
