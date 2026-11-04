import { SAMPLES } from './data/samples'
import CardFrame from './components/card/CardFrame'
import './styles/app.css'

export default function App() {
  const s = SAMPLES[0]
  return (
    <main className="scene" style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
      {s.cards.map((c, i) => (
        <CardFrame key={c.card_id} card={c} index={i} total={s.cards.length} width={240} />
      ))}
    </main>
  )
}
