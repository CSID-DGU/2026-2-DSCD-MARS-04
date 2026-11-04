/** 카드 PNG(1080×1350)와 검수 기록 JSON 저장. 서버 렌더링 API는 준비 중이라 브라우저에서 그린다. */
import { createElement } from 'react'
import CardTemplate from '../components/card/CardTemplate'
import cardCss from '../styles/card.css?raw'
import type { Card } from '../types/domain'

export function saveBlob(blob: Blob, name: string) {
  const a = document.createElement('a')
  const url = URL.createObjectURL(blob)
  a.href = url
  a.download = name
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

async function toDataUrl(src: string): Promise<string> {
  if (src.startsWith('data:')) return src
  const res = await fetch(src)
  const blob = await res.blob()
  return new Promise((r) => {
    const fr = new FileReader()
    fr.onload = () => r(String(fr.result))
    fr.readAsDataURL(blob)
  })
}

/** SVG foreignObject 는 외부 URL 이미지를 못 불러오므로 data URL 로 바꿔 넣는다. */
async function inlineImages(card: Card): Promise<Card> {
  const c = { ...card }
  if (c.image?.data) c.image = { ...c.image, data: await toDataUrl(c.image.data) }
  return c
}

export async function cardToPngBlob(card: Card, index: number, total: number, sourceName?: string): Promise<Blob> {
  const inlined = await inlineImages(card)
  const logo = await toDataUrl('/logo.svg')
  const { renderToStaticMarkup } = await import('react-dom/server')
  const html = renderToStaticMarkup(createElement(CardTemplate, { card: inlined, index, total, sourceName })).replaceAll('src="/logo.svg"', `src="${logo}"`)
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="720" height="900"><foreignObject x="0" y="0" width="720" height="900"><div xmlns="http://www.w3.org/1999/xhtml"><style>${cardCss}</style>${html}</div></foreignObject></svg>`
  const img = new Image()
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
  await img.decode()
  const cv = document.createElement('canvas')
  cv.width = 1080
  cv.height = 1350
  cv.getContext('2d')!.drawImage(img, 0, 0, 1080, 1350)
  const blob = await new Promise<Blob | null>((r) => cv.toBlob(r, 'image/png'))
  if (!blob) throw new Error('png')
  return blob
}
