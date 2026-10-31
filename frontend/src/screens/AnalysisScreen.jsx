import { useEffect, useState } from 'react'
import { CheckIcon } from '../components/Icons'
import { CRITERIA } from '../data'

const STEP_DURATION = 1100
const RADIUS = 92
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export default function AnalysisScreen({ onComplete }) {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const total = STEP_DURATION * CRITERIA.length
    const startedAt = performance.now()
    let frame

    const tick = (now) => {
      const value = Math.min((now - startedAt) / total, 1)
      setProgress(value)
      if (value < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)

    const done = window.setTimeout(onComplete, total + 500)
    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(done)
    }
  }, [onComplete])

  const activeStep = Math.min(Math.floor(progress * CRITERIA.length), CRITERIA.length - 1)
  const isFinished = progress >= 1
  const percent = Math.round(progress * 100)

  return (
    <div className="flow container analysis">
      <div className="analysis-dial stagger" style={{ '--i': 0 }}>
        <svg viewBox="0 0 220 220" aria-hidden="true">
          <circle className="dial-track" cx="110" cy="110" r={RADIUS} />
          <circle
            className="dial-progress"
            cx="110"
            cy="110"
            r={RADIUS}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - progress)}
          />
        </svg>
        <span className="dial-orbit" aria-hidden="true" />
        <div className="dial-value">
          <span className="dial-percent">
            {percent}
            <small>%</small>
          </span>
          <span className="dial-caption">{isFinished ? 'Готово' : 'Анализ'}</span>
        </div>
      </div>

      <div className="analysis-copy">
        <span className="eyebrow stagger" style={{ '--i': 1 }}>
          Шаг 02
        </span>
        <h1 className="flow-title stagger" style={{ '--i': 2 }} aria-live="polite">
          {isFinished ? 'Отчёт готов' : CRITERIA[activeStep].title}
        </h1>
        <p className="flow-lead stagger" style={{ '--i': 3 }}>
          Проверяем каждое допущение плана. Это займёт несколько секунд.
        </p>

        <ol className="analysis-steps stagger" style={{ '--i': 4 }}>
          {CRITERIA.map((item, index) => {
            const state = isFinished || index < activeStep ? 'done' : index === activeStep ? 'active' : 'pending'
            return (
              <li key={item.id} className={`analysis-step is-${state}`}>
                <span className="analysis-step-mark">
                  {state === 'done' ? <CheckIcon /> : String(index + 1).padStart(2, '0')}
                </span>
                <span className="analysis-step-body">
                  <span className="analysis-step-title">{item.title}</span>
                  <span className="analysis-step-text">{item.text}</span>
                </span>
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}
