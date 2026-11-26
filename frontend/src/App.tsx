import type { Session } from '@supabase/supabase-js'
import { useEffect, useRef, useState } from 'react'
import { SourceContext } from './components/card/SourceContext'
import { sourceLabel } from './components/card/util'
import Loading from './components/common/Loading'
import { signIn, supabase } from './lib/supabase'
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
  // 구글 로그인에서 돌아오면 ?start=1 이 붙어 있어 바로 작업 화면을 연다
  const [landing, setLanding] = useState(() => !new URLSearchParams(window.location.search).has('start'))
  const [session, setSession] = useState<Session | null>(null)
  const [expired, setExpired] = useState(false)
  const loggingOut = useRef(false)
  const authOn = !!supabase && wf.mode === 'http'
  const needLogin = authOn && !session

  useEffect(() => {
    if (!supabase) return
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      // Supabase가 주소의 로그인 정보를 읽은 뒤에 표시용 파라미터를 지운다
      if (window.location.search) window.history.replaceState(null, '', window.location.pathname + window.location.hash)
    })
    const { data } = supabase.auth.onAuthStateChange((event, s) => {
      setSession(s)
      if (event === 'SIGNED_IN') setExpired(false)
      if (event === 'SIGNED_OUT') {
        setExpired(!loggingOut.current)
        loggingOut.current = false
      }
    })
    return () => data.subscription.unsubscribe()
  }, [])

  const start = () => (needLogin ? void signIn() : setLanding(false))
  const logout = () => {
    loggingOut.current = true
    void supabase?.auth.signOut()
  }

  // 세션이 끊기면(로그아웃·401) 작업 화면 대신 랜딩을 보여준다
  const onLanding = landing || needLogin
  useEffect(() => {
    document.body.classList.toggle('on-landing', onLanding)
    window.scrollTo(0, 0)
  }, [onLanding])

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
    <SourceContext.Provider value={sourceLabel(wf.document?.source)}>
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
        <div className="header-actions">
          {wf.mode === 'mock' ? <span className="small muted">샘플 데이터</span> : null}
          {expired && needLogin ? <span className="small error">로그인이 만료됐어요. 다시 로그인해 주세요.</span> : null}
          {authOn && session ? (
            <>
              <span className="small muted">{session.user.user_metadata.name ?? session.user.email}</span>
              <button className="header-cta" onClick={logout}>
                로그아웃
              </button>
            </>
          ) : authOn ? (
            <button className="gsi-btn" onClick={() => void signIn()} aria-label="Sign in with Google">
              <svg viewBox="0 0 48 48" aria-hidden="true">
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
                <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
                <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
              </svg>
              <span>Sign in with Google</span>
            </button>
          ) : null}
        </div>
      </header>
      <Landing onStart={start} />
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
    </SourceContext.Provider>
  )
}
