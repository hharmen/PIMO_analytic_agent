import { CRITERIA, statusLabel } from '../data'

function Trace({ trace, title }) {
  if (!trace?.steps?.length) return null
  return <div className="trace"><h4>{title}</h4><ol>{trace.steps.map((step, index) => (
    <li key={index}><strong>{step.number}. {step.transition || 'Начальное состояние'}</strong><pre>{JSON.stringify(step.state, null, 2)}</pre></li>
  ))}</ol></div>
}

function Issues({ issues }) {
  if (!issues?.length) return null
  return <ul className="check-issues">{issues.map((issue, index) => <li key={index}>{issue.path && <code>{issue.path}: </code>}{issue.message}</li>)}</ul>
}

function CheckRun({ run }) {
  const result = run.result_json
  return (
    <article className={`check-run status-${run.status}`}>
      <div className="report-main-head"><h3>{statusLabel(run.status)}</h3><span>Проверка #{run.id}</span></div>
      <p className="submit-note">{new Date(run.created_at).toLocaleString('ru-RU')} · Движок: {result.engine || 'TLC'}</p>
      {run.status === 'PROPERTY_HOLDS'
        ? <p>Свойства выполнены в исследованной конечной модели при заданных ограничениях. Это не доказывает корректность реальной системы.</p>
        : <p>{run.status === 'PROPERTY_VIOLATED' ? 'Проверка обнаружила нарушение свойства. Изучите сценарий и объяснение агента.' : 'Успешная проверка всех свойств не подтверждена. Изучите детали результата.'}</p>}
      <Issues issues={result.errors} />
      {(result.results || []).map((property) => {
        const properties = Array.isArray(run.model_json.properties) ? run.model_json.properties : []
        const definition = properties.find((item) => item?.id === property.property_id)
        return <section className={`property-result status-${property.status}`} key={property.property_id}>
          <h4>{property.property_id} · {CRITERIA.find((item) => item.id === property.property_type)?.title || property.property_type}</h4>
          <p><strong>{statusLabel(property.status)}</strong></p>
          {definition?.description && <p>{definition.description}</p>}
          <p>{property.message}</p>
          {property.related_requirements?.length > 0 && <div><strong>Связанные требования</strong><ul>{property.related_requirements.map((text, index) => <li key={index}>{text}</li>)}</ul></div>}
          <Issues issues={property.errors} />
          <Trace trace={property.counterexample} title="Контрпример: путь к нарушению" />
          <Trace trace={property.witness} title="Пример пути к цели" />
          {property.statistics && <dl className="check-statistics">{Object.entries(property.statistics).filter(([, value]) => value !== null).map(([key, value]) => <div key={key}><dt>{({ states_generated: 'Сгенерировано состояний', distinct_states: 'Уникальных состояний', depth: 'Глубина' })[key] || key}</dt><dd>{value}</dd></div>)}</dl>}
          {property.engine_output && <details><summary>Вывод движка</summary><pre>{property.engine_output}</pre></details>}
        </section>
      })}
      <details><summary>Построенная модель JSON</summary><pre>{JSON.stringify(run.model_json, null, 2)}</pre></details>
      <details><summary>Полный результат проверки JSON</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
    </article>
  )
}

export default function ReportScreen({ chat, messages, checks, onEdit, onRestart, disabled }) {
  return (
    <div className="flow container">
      <div className="report-main-head"><div><span className="eyebrow">Диалог с агентом</span><h1 className="chat-title">{chat.title}</h1></div><button type="button" className="ghost-btn" disabled={disabled} onClick={onRestart}>Новый чат</button></div>
      <div className="conversation-layout">
        <section aria-label="Переписка" className="conversation">
          {!messages.length && <p>В этом чате ещё нет сообщений. Добавьте требования для проверки.</p>}
          {messages.map((message) => <article className={`message message-${message.role}`} key={message.id}>
            <div className="message-heading"><strong>{message.role === 'user' ? 'Вы' : 'Агент-аналитик'}</strong><time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString('ru-RU')}</time></div>
            <div className="message-content">{message.content}</div>
          </article>)}
          <button type="button" className="primary-btn" disabled={disabled} onClick={onEdit}>Уточнить требования / продолжить</button>
        </section>
        <section aria-label="История проверок" className="checks">
          <h2>История проверок · {checks.length}</h2>
          {!checks.length && <p className="empty-state">Проверок пока нет. Агент может запросить уточнение или сообщить о недоступности проверки. Ответ без результата TLC не означает, что свойства выполнены.</p>}
          {[...checks].reverse().map((run) => <CheckRun key={run.id} run={run} />)}
        </section>
      </div>
    </div>
  )
}
