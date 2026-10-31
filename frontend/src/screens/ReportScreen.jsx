import { useCountUp } from '../hooks'
import { ArrowLeftIcon } from '../components/Icons'
import { LEVEL_LABEL } from '../data'

function ScoreCard({ score, risks }) {
  const value = useCountUp(score, { decimals: 1, duration: 1400 })
  const counts = risks.reduce((acc, risk) => ({ ...acc, [risk.level]: (acc[risk.level] ?? 0) + 1 }), {})

  return (
    <div className="score-card">
      <span className="score-card-label">Общий уровень риска</span>
      <span className="score-card-value">
        {value.toLocaleString('ru-RU', { minimumFractionDigits: 1 })}
        <small>/10</small>
      </span>
      <div className="score-bar" aria-hidden="true">
        {Array.from({ length: 10 }, (_, i) => (
          <span key={i} className={i < Math.round(score) ? 'is-filled' : ''} style={{ '--i': i }} />
        ))}
      </div>
      <dl className="score-counts">
        {['high', 'medium', 'low'].map((level) => (
          <div key={level}>
            <dt>{LEVEL_LABEL[level]}</dt>
            <dd>{counts[level] ?? 0}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

export default function ReportScreen({ report, onEdit, onRestart }) {
  return (
    <div className="flow container">
      <button type="button" className="back-btn stagger" style={{ '--i': 0 }} onClick={onEdit}>
        <ArrowLeftIcon />
        Изменить описание
      </button>

      <div className="report-layout">
        <aside className="report-aside">
          <span className="eyebrow stagger" style={{ '--i': 1 }}>
            Шаг 03
          </span>
          <h1 className="flow-title stagger" style={{ '--i': 2 }}>
            Результаты
            <br />
            анализа
          </h1>
          <div className="stagger" style={{ '--i': 3 }}>
            <ScoreCard score={report.score} risks={report.risks} />
          </div>
          <p className="report-summary stagger" style={{ '--i': 4 }}>
            {report.summary}
          </p>
          <button type="button" className="primary-btn stagger" style={{ '--i': 5 }} onClick={onRestart}>
            <span>Новая проверка</span>
          </button>
        </aside>

        <section className="report-main">
          <div className="report-main-head stagger" style={{ '--i': 2 }}>
            <h2>Найденные риски</h2>
            <span>{report.risks.length} пункта</span>
          </div>
          <ol className="risk-list">
            {report.risks.map((risk, index) => (
              <li key={risk.title} className={`risk-card risk-${risk.level} stagger`} style={{ '--i': index + 3 }}>
                <div className="risk-card-top">
                  <span className="risk-index">{String(index + 1).padStart(2, '0')}/</span>
                  <span className={`level level-${risk.level}`}>{LEVEL_LABEL[risk.level]}</span>
                  <span className="risk-area">{risk.area}</span>
                </div>
                <h3>{risk.title}</h3>
                <p>{risk.text}</p>
                <div className="risk-advice">
                  <span>Рекомендация</span>
                  <p>{risk.advice}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  )
}
