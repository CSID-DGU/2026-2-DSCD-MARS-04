import { createContext } from 'react'

/** 카드 하단 출처 표기. App 에서 현재 문서 기준으로 채운다. */
export const SourceContext = createContext<string>('원문')
