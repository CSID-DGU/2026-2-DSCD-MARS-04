import type { CardImage } from '../../types/domain'

/** 원문 URL 도메인 → 출처 이름. 모르는 도메인은 도메인 그대로 쓴다. */
const KNOWN_SOURCES: Record<string, string> = {
  'korea.kr': '대한민국 정책브리핑',
  'yna.co.kr': '연합뉴스',
  'bbc.com': 'BBC',
}

export function sourceLabel(source: { source_name?: string | null; source_url?: string | null } | null | undefined): string {
  if (source?.source_name?.trim()) return source.source_name.trim()
  if (source?.source_url) {
    try {
      const host = new URL(source.source_url).hostname.replace(/^www\./, '')
      const known = Object.entries(KNOWN_SOURCES).find(([d]) => host === d || host.endsWith('.' + d))
      return known ? known[1] : host
    } catch {
      /* 잘못된 URL은 아래 기본값 */
    }
  }
  return '원문'
}

export function credit(image: CardImage | undefined, sourceName = '원문'): string {
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
