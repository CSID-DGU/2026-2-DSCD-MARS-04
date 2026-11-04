import type { CardStatus } from '../../types/domain'

export const STATUS: Record<CardStatus, { label: string; color: string; bg: string }> = {
  ok: { label: '원문과 일치', color: '#0866d9', bg: '#e8f1ff' },
  warn: { label: '확인 필요', color: '#8a4f00', bg: '#fff1dc' },
  bad: { label: '의미 달라짐', color: '#b3261e', bg: '#fdeceb' },
  pending: { label: '수정됨 · 재검사 필요', color: '#5f6877', bg: '#eef1f5' },
  unchecked: { label: '미검사', color: '#5f6877', bg: '#eef1f5' },
}
