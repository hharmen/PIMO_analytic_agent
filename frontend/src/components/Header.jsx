import { STEPS } from '../data'
import StartButton from './StartButton'

function Stepper({ current }) {
  const currentIndex = STEPS.findIndex((step) => step.id === current)

  return (
    <ol className="stepper" aria-label="Этапы проверки">
      {STEPS.map((step, index) => {
        const state = index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'upcoming'
        return (
          <li key={step.id} className={`stepper-item is-${state}`} aria-current={state === 'current' ? 'step' : undefined}>
            <span className="stepper-index">{String(index + 1).padStart(2, '0')}</span>
            <span className="stepper-title">{step.title}</span>
          </li>
        )
      })}
    </ol>
  )
}

export default function Header({ route, onNavigate }) {
  const isLanding = route === 'landing'

  function scrollTo(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <button type="button" className="brand" onClick={() => onNavigate('landing')}>
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">PIMO</span>
        </button>

        {isLanding ? (
          <nav className="topnav" aria-label="Разделы">
            <button type="button" onClick={() => scrollTo('how')}>Как это работает</button>
            <button type="button" onClick={() => scrollTo('criteria')}>Что проверяем</button>
          </nav>
        ) : (
          <Stepper current={route} />
        )}

        {isLanding ? (
          <StartButton size="sm" variant="outline" className="topbar-cta" onClick={() => onNavigate('input')} />
        ) : (
          <span className="topbar-meta">Учебный проект</span>
        )}
      </div>
    </header>
  )
}
