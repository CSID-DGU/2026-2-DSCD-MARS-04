import { useEffect, useState } from 'react'

const LAYERS = [
  ['모든 문구의 출발점, 원문.', '카드를 만들고 수정해도 근거가 된 문장은 그대로 남습니다.'],
  ['전하고 싶은 정보를 직접 선택.', '선택한 묶음과 원문을 연결해 어떤 내용이 카드에 쓰였는지 살펴봅니다.'],
  ['결과물에서 다시 근거로.', '카드 문구를 확인하고, 원문과 비교해 수정한 뒤 다시 검사합니다.'],
]

export default function Landing({ onStart }: { onStart: () => void }) {
  const [layer, setLayer] = useState(0)
  const [compared, setCompared] = useState(false)

  useEffect(() => {
    if (!('IntersectionObserver' in window)) return
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('seen')
            io.unobserve(e.target)
          }
        }),
      { threshold: 0.3 },
    )
    document.querySelectorAll('#proof,#journey').forEach((e) => io.observe(e))
    return () => io.disconnect()
  }, [])

  const layerBtn = (n: number, cls: string, children: React.ReactNode, label: string) => (
    <button className={`${cls} ${layer === n ? 'active' : ''}`} onClick={() => setLayer(n)} aria-label={label} aria-pressed={layer === n}>
      {children}
    </button>
  )

  return (
    <section id="landing">
      <div className="landing-hero">
        <div className="hero-copy">
          <h1>
            짧아진 문장에도,
            <br />
            <em>근거는 남도록.</em>
          </h1>
          <p>
            원문에서 고른 정보가 카드뉴스가 되기까지.
            <br />
            CardSync는 선택한 내용과 원문을 연결해
            <br />
            제작과 검수를 하나의 흐름으로 만듭니다.
          </p>
          <div className="hero-actions">
            <button className="primary start" onClick={onStart}>
              카드뉴스 만들기 <span aria-hidden="true">↗</span>
            </button>
            <a href="#why">어떻게 연결되나요?</a>
          </div>
        </div>
        <div className="explainer" aria-label="원문, 정보 묶음, 카드의 세 층 구조">
          <div className="stack-stage" id="stack">
            <svg className="stack-links" viewBox="0 0 600 580" aria-hidden="true">
              <path d="M155 405 L155 215 M300 450 L300 170 M440 400 L440 215" />
              <path className="travel" d="M155 405 L155 215 M300 450 L300 170 M440 400 L440 215" />
            </svg>
            {layerBtn(
              0,
              'plane plane-source',
              <>
                <span className="plane-heading">
                  SOURCE <span>S1 — S4</span>
                </span>
                <div className="paperlines">
                  <i />
                  <i />
                  <i />
                  <i />
                  <i />
                </div>
                <span className="source-mark">원문</span>
              </>,
              '원문 층 설명',
            )}
            {layerBtn(
              1,
              'plane plane-groups',
              <>
                <span className="plane-heading">SELECTED INFORMATION</span>
                <div className="group-chips">
                  <span>대상·지원금</span>
                  <span>신청 기간</span>
                  <span>유의사항</span>
                </div>
              </>,
              '정보 묶음 층 설명',
            )}
            {layerBtn(
              2,
              'plane plane-cards',
              <>
                <span className="plane-heading">YOUR CARD NEWS</span>
                <div className="mini-cards">
                  <div>
                    <b>
                      청년 주거
                      <br />
                      지원 안내
                    </b>
                    <i />
                    <i />
                  </div>
                  <div>
                    <b>신청 기간</b>
                    <i />
                    <i />
                  </div>
                  <div>
                    <b>
                      신청 전<br />
                      확인하세요
                    </b>
                    <i />
                  </div>
                </div>
              </>,
              '카드 층 설명',
            )}
          </div>
          <div className="layer-controls" aria-label="설명할 층 선택">
            {['원문', '정보 묶음', '카드뉴스'].map((t, i) => (
              <span key={t} style={{ display: 'contents' }}>
                {i ? <span aria-hidden="true">→</span> : null}
                <button className={layer === i ? 'active' : ''} onClick={() => setLayer(i)}>
                  {t}
                </button>
              </span>
            ))}
          </div>
          <div className="layer-caption" aria-live="polite">
            <b>{LAYERS[layer][0]}</b>
            <p>{LAYERS[layer][1]}</p>
          </div>
        </div>
      </div>
      <section className="story-section" id="why">
        <div className="story-copy">
          <h2>
            예쁘게 줄이는 것과
            <br />
            정확히 전하는 것은
            <br />
            <span>다른 일이니까.</span>
          </h2>
          <p>
            ‘최대’ 한 단어, 지원 대상 한 줄.
            <br />
            짧게 다듬는 사이 의미가 달라질 수 있습니다.
            <br />
            문제가 있는 문구에서 바로 원문을 확인하세요.
          </p>
        </div>
        <div className={`proof ${compared ? 'fixed' : ''}`} id="proof">
          <div className="proof-label">카드 문구</div>
          <p className="claim">
            {compared ? (
              <>
                소득 기준을 충족한 무주택 청년에게
                <br />월 최대 20만 원을 지원합니다.
              </>
            ) : (
              <>
                청년은 <mark>누구나</mark>
                <br />
                매달 20만 원을 받습니다.
              </>
            )}
          </p>
          <div className="proof-state">{compared ? '원문의 대상 조건과 금액 표현을 반영한 문구' : '조건 확인이 필요한 문구'}</div>
          <div className="evidence-line">
            <span>근거 원문</span>
            <p>
              소득 기준을 충족한 무주택 청년에게
              <br />월 <strong>최대 20만 원</strong>을 지원한다.
            </p>
          </div>
          <button onClick={() => setCompared((c) => !c)}>{compared ? '수정 전 문구와 비교' : '원문을 반영하면 어떻게 될까요?'}</button>
        </div>
      </section>
      <section className="flow-section" id="journey">
        <h2>
          다른 도구로 옮기지 않고,
          <br />
          하나의 제작 흐름에서.
        </h2>
        <div className="journey">
          {[
            ['01', '담을 정보를 고르고', '원문을 넣고 필요한 묶음을 선택합니다.'],
            ['02', '카드에서 다듬고', '문구와 근거를 같은 화면에서 확인합니다.'],
            ['03', '수정한 뒤 다시 확인', '바뀐 문구에는 새 검사 상태를 연결합니다.'],
            ['04', '독자의 눈으로 마무리', '게시 미리보기 후 이미지로 저장합니다.'],
          ].map(([n, h, p]) => (
            <div key={n}>
              <span>{n}</span>
              <h3>{h}</h3>
              <p>{p}</p>
            </div>
          ))}
        </div>
      </section>
      <section className="closing">
        <div>
          <h2>
            원문 하나로,
            <br />
            끝까지 만들어 보세요.
          </h2>
          <p>원문을 붙여넣으면 바로 시작할 수 있습니다.</p>
        </div>
        <button className="primary start" onClick={onStart}>
          제작 시작하기 ↗
        </button>
      </section>
    </section>
  )
}
