import Reveal from '../components/Reveal'
import StartButton from '../components/StartButton'
import { CRITERIA } from '../data'

const HOW_STEPS = [
  {
    title: 'Опишите требования',
    text: 'Вставьте описание поведения системы или импортируйте текст из TXT.',
  },
  {
    title: 'Дождитесь анализа',
    text: 'LLM построит модель состояний и переходов, а TLC проверит её свойства.',
  },
  {
    title: 'Получите отчёт',
    text: 'Объяснение агента, результат проверки и путь к нарушению, если оно найдено.',
  },
]

const FACTS = [
  { value: '4', label: 'типа проверяемых свойств' },
  { value: 'TLC', label: 'детерминированный движок' },
  { value: 'LLM', label: 'интерпретация требований' },
]

const PREVIEW_LINES = [
  { width: 92 },
  { width: 78 },
  { width: 86, flag: 900 },
  { width: 64 },
  { width: 0 },
  { width: 88 },
  { width: 72 },
  { width: 95 },
  { width: 58, flag: 2100 },
  { width: 0 },
  { width: 82 },
  { width: 69 },
  { width: 90 },
  { width: 46 },
]

function HeroPreview() {
  return (
    <div className="preview" aria-hidden="true">
      <div className="preview-backdrop" />
      <div className="preview-sheet">
        <div className="preview-head">
          <span className="preview-dot" />
          <span className="preview-label">requirements.txt</span>
        </div>
        <div className="preview-lines">
          {PREVIEW_LINES.map((line, i) =>
            line.width ? (
              <span
                key={i}
                className={`preview-line${line.flag ? ' is-flagged' : ''}`}
                style={{ width: `${line.width}%`, '--flag-delay': `${line.flag}ms` }}
              />
            ) : (
              <span key={i} className="preview-gap" />
            ),
          )}
        </div>
        <span className="preview-scan" />
      </div>

      <div className="preview-note preview-note-1">
        <span className="level level-high">Нарушение</span>
        <span>Исполнение после отмены</span>
      </div>
      <div className="preview-note preview-note-2">
        <span className="level level-medium">Сценарий</span>
        <span>Approve → Cancel → Execute</span>
      </div>
      <div className="preview-score">
        <span className="preview-score-label">Пример проверки</span>
        <span className="preview-score-value">
          P1<span> · нарушено</span>
        </span>
      </div>
    </div>
  )
}

export default function Landing({ onStart }) {
  return (
    <div className="landing">
      <section className="hero container">
        <div className="hero-copy">
          <span className="eyebrow hero-in" style={{ '--d': '0ms' }}>
            Проверка логики требований
          </span>
          <h1 className="hero-title">
            <span className="line">
              <span style={{ '--d': '80ms' }}>Найдите ошибки</span>
            </span>
            <span className="line">
              <span style={{ '--d': '160ms' }}>в требованиях</span>
            </span>
            <span className="line">
              <em style={{ '--d': '240ms' }}>до разработки</em>
            </span>
          </h1>
          <p className="hero-lead hero-in" style={{ '--d': '420ms' }}>
            PIMO превращает описание поведения системы в формальную модель,
            проверяет её свойства и объясняет найденные противоречия.
          </p>
          <div className="hero-actions hero-in" style={{ '--d': '520ms' }}>
            <StartButton onClick={onStart} />
            <button
              type="button"
              className="text-btn"
              onClick={() => document.getElementById('how')?.scrollIntoView({ behavior: 'smooth' })}
            >
              Как это работает
            </button>
          </div>
        </div>

        <div className="hero-visual hero-in" style={{ '--d': '300ms' }}>
          <HeroPreview />
        </div>
      </section>

      <section className="facts container">
        {FACTS.map((fact, i) => (
          <Reveal key={fact.label} className="fact" delay={i * 90}>
            <span className="fact-value">{fact.value}</span>
            <span className="fact-label">{fact.label}</span>
          </Reveal>
        ))}
      </section>

      <section id="how" className="section container">
        <Reveal className="section-head">
          <span className="eyebrow">Как это работает</span>
          <h2 className="section-title">Три шага до отчёта</h2>
        </Reveal>
        <ol className="how">
          {HOW_STEPS.map((step, i) => (
            <Reveal as="li" key={step.title} className="how-item" delay={i * 120}>
              <span className="how-index">{String(i + 1).padStart(2, '0')}</span>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </Reveal>
          ))}
        </ol>
      </section>

      <section id="criteria" className="section container">
        <div className="criteria-split">
          <Reveal className="criteria-aside">
            <span className="eyebrow eyebrow-light">Что проверяем</span>
            <h2>
              Четыре
              <br />
              типа
              <br />
              свойств
            </h2>
          </Reveal>
          <ul className="criteria-rows">
            {CRITERIA.map((item, i) => (
              <Reveal as="li" key={item.id} className="criteria-row" delay={i * 90}>
                <span className="criteria-row-index">{String(i + 1).padStart(2, '0')}/</span>
                <div>
                  <h3>{item.title}</h3>
                  <p>{item.details}</p>
                </div>
              </Reveal>
            ))}
          </ul>
        </div>
      </section>

      <section className="container">
        <Reveal className="cta-band">
          <h2>Проверьте логику требований</h2>
          <p>Войдите в аккаунт, чтобы сохранить переписку и результаты проверок.</p>
          <StartButton onClick={onStart} />
        </Reveal>
      </section>
    </div>
  )
}
