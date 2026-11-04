/** 제작 흐름 상태: 단계·문서·선택 묶음·카드·작업 진행. 서버 호출은 전부 여기서. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, resolveApi, waitJob, type CardSyncApi, type DocumentIn, type SourceOption } from '../api'
import type { Card, CardFields, Document, ExportRecord } from '../types/domain'

export const STEP_NAMES = ['원문 입력', '정보 선택', '카드 편집', '검사 결과', '게시 미리보기', '다운로드'] as const
export type Step = 0 | 1 | 2 | 3 | 4 | 5
export type BusyKind = 'analysis' | 'generation' | 'check'

export interface Busy {
  kind: BusyKind
  stage: string | null
}

export interface Workflow {
  ready: boolean
  mode: 'http' | 'mock' | null
  fallback: boolean
  step: Step
  maxStep: Step
  busy: Busy | null
  error: string | null
  sources: SourceOption[]
  document: Document | null
  selected: Set<string>
  cards: Card[]
  current: number
  reader: number
  checkFailed: boolean
  go: (n: Step) => void
  setCurrent: (i: number) => void
  setReader: (i: number) => void
  clearError: () => void
  pickSource: (key: string) => Promise<DocumentIn | null>
  analyze: (body: DocumentIn) => Promise<void>
  toggleGroup: (id: string) => void
  selectAll: () => void
  selectNone: () => void
  generate: () => Promise<void>
  editCard: (cardId: string, fields: Partial<CardFields>) => Promise<void>
  setCardImage: (cardId: string, image: Card['image']) => void
  applyRepair: (cardId: string) => Promise<void>
  inspect: (cardIds?: string[]) => Promise<void>
  simulateCheckFailure: () => void
  record: () => Promise<ExportRecord>
  reset: () => void
}

export function useWorkflow(): Workflow {
  const apiRef = useRef<CardSyncApi | null>(null)
  const [ready, setReady] = useState(false)
  const [fallback, setFallback] = useState(false)
  const [sources, setSources] = useState<SourceOption[]>([])
  const [step, setStep] = useState<Step>(0)
  const [maxStep, setMaxStep] = useState<Step>(0)
  const [busy, setBusy] = useState<Busy | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [document, setDocument] = useState<Document | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [cards, setCards] = useState<Card[]>([])
  const [current, setCurrent] = useState(0)
  const [reader, setReader] = useState(0)
  const [checkFailed, setCheckFailed] = useState(false)

  useEffect(() => {
    let alive = true
    resolveApi()
      .then(async ({ api, fallback }) => {
        if (!alive) return
        apiRef.current = api
        setFallback(fallback)
        setSources(await api.sources())
        setReady(true)
      })
      .catch((e: Error) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [])

  const api = () => {
    if (!apiRef.current) throw new ApiError(0, '아직 준비 중이에요.')
    return apiRef.current
  }

  const go = useCallback((n: Step) => {
    setStep(n)
    setMaxStep((m) => (n > m ? n : m))
    window.scrollTo(0, 0)
  }, [])

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e))

  async function run<T>(kind: BusyKind, jobOf: () => Promise<string>, after: () => Promise<T>): Promise<T | undefined> {
    setBusy({ kind, stage: null })
    try {
      const jobId = await jobOf()
      await waitJob(api(), jobId, (stage) => setBusy({ kind, stage }))
      return await after()
    } catch (e) {
      fail(e)
      return undefined
    } finally {
      setBusy(null)
    }
  }

  const refreshCards = async (docId: string) => {
    const list = await api().listCards(docId)
    setCards(list)
    return list
  }

  const analyze = async (body: DocumentIn) => {
    setError(null)
    if (cards.length && !window.confirm('원문을 바꾸면 만든 카드와 검사 결과가 초기화돼요. 계속할까요?')) return
    setBusy({ kind: 'analysis', stage: null })
    try {
      const started = await api().createDocument(body)
      await waitJob(api(), started.job_id, (stage) => setBusy({ kind: 'analysis', stage }))
      const doc = await api().getDocument(started.document_id)
      setDocument(doc)
      setSelected(new Set(doc.groups.map((g) => g.group_id)))
      setCards([])
      setMaxStep(0)
      setCheckFailed(false)
      go(1)
    } catch (e) {
      fail(e)
    } finally {
      setBusy(null)
    }
  }
  const generate = async () => {
    if (!document) return
    if (cards.length && !window.confirm('카드를 새로 만들면 고친 문구와 검사 결과가 초기화돼요. 계속할까요?')) return
    setError(null)
    const ids = document.groups.map((g) => g.group_id).filter((g) => selected.has(g))
    if (!ids.length) {
      setError('카드에 담을 정보 묶음을 하나 이상 골라 주세요.')
      return
    }
    await run(
      'generation',
      async () => {
        await api().putSelection(document.document_id, ids)
        return (await api().createCards(document.document_id, cards.length > 0)).job_id
      },
      async () => {
        await refreshCards(document.document_id)
        setDocument((d) => (d ? { ...d, required_group_ids: ids } : d))
        setCurrent(0)
        setReader(0)
        setCheckFailed(false)
        go(2)
      },
    )
  }

  const editCard = async (cardId: string, fields: Partial<CardFields>) => {
    if (!document) return
    const card = cards.find((c) => c.card_id === cardId)
    if (!card) return
    try {
      const updated = await api().patchCard(document.document_id, cardId, card.version, fields)
      setCards((cs) => cs.map((c) => (c.card_id === cardId ? { ...c, ...updated, image: c.image, repair: c.repair } : c)))
    } catch (e) {
      fail(e)
      if (e instanceof ApiError && e.code === 409) await refreshCards(document.document_id)
    }
  }

  const setCardImage = (cardId: string, image: Card['image']) =>
    setCards((cs) => cs.map((c) => (c.card_id === cardId ? { ...c, image } : c)))

  const applyRepair = async (cardId: string) => {
    const card = cards.find((c) => c.card_id === cardId)
    if (!card?.repair) return
    await editCard(cardId, card.repair.fields)
  }

  const inspect = async (cardIds?: string[]) => {
    if (!document) return
    setError(null)
    setCheckFailed(false)
    await run(
      'check',
      async () => (await api().createChecks(document.document_id, cardIds)).job_id,
      async () => {
        await refreshCards(document.document_id)
        go(3)
      },
    )
  }

  const simulateCheckFailure = () => {
    setBusy({ kind: 'check', stage: null })
    setTimeout(() => {
      setBusy(null)
      setCheckFailed(true)
      go(3)
    }, 1500)
  }

  const record = () => api().record(document!.document_id)

  const reset = () => {
    setStep(0)
    setMaxStep(0)
    setDocument(null)
    setSelected(new Set())
    setCards([])
    setCurrent(0)
    setReader(0)
    setCheckFailed(false)
    setError(null)
  }

  const toggleGroup = (id: string) =>
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })

  return useMemo<Workflow>(
    () => ({
      ready,
      mode: apiRef.current?.mode ?? null,
      fallback,
      step,
      maxStep,
      busy,
      error,
      sources,
      document,
      selected,
      cards,
      current,
      reader,
      checkFailed,
      go,
      setCurrent,
      setReader,
      clearError: () => setError(null),
      pickSource: (key) => api().sourceText(key),
      analyze,
      toggleGroup,
      selectAll: () => setSelected(new Set(document?.groups.map((g) => g.group_id) ?? [])),
      selectNone: () => setSelected(new Set()),
      generate,
      editCard,
      setCardImage,
      applyRepair,
      inspect,
      simulateCheckFailure,
      record,
      reset,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ready, fallback, step, maxStep, busy, error, sources, document, selected, cards, current, reader, checkFailed],
  )
}
