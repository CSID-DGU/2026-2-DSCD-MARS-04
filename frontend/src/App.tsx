import { useEffect, useState } from 'react'
import Loading from './components/common/Loading'
import { STEP_NAMES, useWorkflow, type Step } from './hooks/useWorkflow'
import CheckView from './views/CheckView'
import DownloadView from './views/DownloadView'
import EditView from './views/EditView'
import GroupsView from './views/GroupsView'
import InputView from './views/InputView'
import Landing from './views/Landing'
import PreviewView from './views/PreviewView'
import './styles/app.css'

export default function App() {
  const wf = useWorkflow()
  const [landing, setLanding] = useState(true)

  useEffect(() => {
    document.body.classList.toggle('on-landing', landing)
    document.title = landing ? 'CardSync — 짧아진 문장에도 근거는 남도록' : 'CardSync — 제작 작업대'
    window.scrollTo(0, 0)
  }, [landing])

  // Alt+Shift+F: 검사 실패 상태 시연 (데모 기능)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!e.altKey || !e.shiftKey || e.code !== 'KeyF' || /INPUT|TEXTAREA/.test((document.activeElement as HTMLElement)?.tagName ?? '')) return
      if (wf.step === 2 && !wf.busy) {
        e.preventDefault()
        wf.simulateCheckFailure()
      }
    }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [wf])

  const views = [InputView, GroupsView, EditView, CheckView, PreviewView, DownloadView]
  const View = views[wf.step]
  const canShow = wf.step === 0 || (wf.document && (wf.step === 1 || wf.cards.length))

  return (
    <>
      <header className="app-header">
        <a
          className="brand"
          id="home-link"
          href="#landing"
          aria-label="CardSync 랜딩으로"
          onClick={(e) => {
            e.preventDefault()
            setLanding(true)
          }}
        >
          <img src="/logo.svg" alt="" />
          CardSync
        </a>
        {wf.mode ? <span className="small muted">{wf.mode === 'mock' ? '샘플 데이터' : '백엔드 연결'}</span> : null}
      </header>
      <Landing onStart={() => setLanding(false)} />
      <nav className="steps" id="steps" aria-label="제작 단계">
        {STEP_NAMES.map((name, i) => (
          <button key={name} disabled={i > wf.maxStep || !!wf.busy} className={wf.step === i ? 'active' : ''} aria-current={wf.step === i ? 'step' : undefined} onClick={() => wf.go(i as Step)}>
            {i + 1} {name}
          </button>
        ))}
      </nav>
      <main id="app" className="scene">
        {!wf.ready ? (
          <p className="muted">{wf.error ?? '준비 중…'}</p>
        ) : wf.busy ? (
          <Loading key={wf.busy.kind} kind={wf.busy.kind} />
        ) : canShow ? (
          <View wf={wf} />
        ) : (
          <InputView wf={wf} />
        )}
      </main>
    </>
  )
}
