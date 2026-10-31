export default function AnalysisScreen() {
  return (
    <div className="flow container analysis" role="status" aria-live="polite" aria-busy="true">
      <div className="waiting-spinner" aria-hidden="true" />
      <div className="analysis-copy">
        <span className="eyebrow">Шаг 02</span>
        <h1 className="flow-title">Агент анализирует требования</h1>
        <p className="flow-lead">Агент строит формальную модель, передаёт её на проверку и готовит объяснение. Если данных недостаточно, он задаст уточняющий вопрос.</p>
        <p>Обработка может занять несколько минут. Дождитесь ответа: он будет сохранён в чате.</p>
      </div>
    </div>
  )
}
