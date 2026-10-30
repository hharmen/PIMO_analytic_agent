import { useRef, useState } from 'react'
import { ArrowIcon, ArrowLeftIcon, CheckIcon, CloseIcon, DocIcon } from '../components/Icons'
import { EXAMPLE_TEXT, INPUT_TIPS, MAX_CHARS } from '../data'

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
}

export default function InputScreen({ text, onTextChange, file, onFileChange, onSubmit, onBack }) {
  const inputRef = useRef(null)
  const [isDragging, setIsDragging] = useState(false)
  const canSubmit = text.trim().length > 0 || Boolean(file)
  const fill = Math.min(text.length / MAX_CHARS, 1)

  function handleDrop(event) {
    event.preventDefault()
    setIsDragging(false)
    const dropped = event.dataTransfer.files?.[0]
    if (dropped) onFileChange(dropped)
  }

  return (
    <div className="flow container">
      <button type="button" className="back-btn stagger" style={{ '--i': 0 }} onClick={onBack}>
        <ArrowLeftIcon />
        На главную
      </button>

      <div className="input-layout">
        <aside className="input-aside">
          <span className="eyebrow stagger" style={{ '--i': 1 }}>
            Шаг 01
          </span>
          <h1 className="flow-title stagger" style={{ '--i': 2 }}>
            Расскажите
            <br />о проекте
          </h1>
          <p className="flow-lead stagger" style={{ '--i': 3 }}>
            Опишите идею своими словами или загрузите готовый документ. Чем больше
            конкретики, тем точнее анализ.
          </p>
        </aside>

        <div className="tips stagger" style={{ '--i': 4 }}>
          <span className="tips-title">Что стоит указать</span>
          <ul>
            {INPUT_TIPS.map((tip) => (
              <li key={tip}>
                <CheckIcon />
                {tip}
              </li>
            ))}
          </ul>
        </div>

        <form
          className="form-card stagger"
          style={{ '--i': 2 }}
          onSubmit={(event) => {
            event.preventDefault()
            if (canSubmit) onSubmit()
          }}
        >
          <div className="field">
            <div className="field-head">
              <label htmlFor="plan" className="field-label">
                <span className="field-index">01</span>
                Описание проекта
              </label>
              <button type="button" className="link-btn" onClick={() => onTextChange(EXAMPLE_TEXT)}>
                Вставить пример
              </button>
            </div>
            <textarea
              id="plan"
              className="textarea"
              value={text}
              onChange={(event) => onTextChange(event.target.value.slice(0, MAX_CHARS))}
              placeholder="Идея, целевая аудитория, конкуренты, бюджет, каналы продаж, ожидаемые показатели…"
              rows={9}
            />
            <div className="field-foot">
              <span className="meter" aria-hidden="true">
                <span style={{ transform: `scaleX(${fill})` }} />
              </span>
              <span className="counter">
                {text.length.toLocaleString('ru-RU')} / {MAX_CHARS.toLocaleString('ru-RU')}
              </span>
            </div>
          </div>

          <div className="field">
            <div className="field-head">
              <span className="field-label">
                <span className="field-index">02</span>
                Документ
                <span className="field-optional">необязательно</span>
              </span>
            </div>

            {file ? (
              <div className="file-chip" key="chip">
                <span className="file-icon">
                  <DocIcon />
                </span>
                <span className="file-info">
                  <span className="file-name">{file.name}</span>
                  <span className="file-size">{formatSize(file.size)}</span>
                </span>
                <button type="button" className="icon-btn" onClick={() => onFileChange(null)} aria-label="Удалить файл">
                  <CloseIcon />
                </button>
              </div>
            ) : (
              <div
                key="drop"
                className={`dropzone${isDragging ? ' is-dragging' : ''}`}
                onDragOver={(event) => {
                  event.preventDefault()
                  setIsDragging(true)
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
              >
                <span className="file-icon">
                  <DocIcon />
                </span>
                <span className="dropzone-text">
                  <span>Перетащите файл сюда</span>
                  <span className="dropzone-hint">PDF, DOCX или TXT — до 20 МБ</span>
                </span>
                <button type="button" className="ghost-btn" onClick={() => inputRef.current?.click()}>
                  Выбрать
                </button>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".pdf,.docx,.txt"
                  hidden
                  onChange={(event) => {
                    const picked = event.target.files?.[0]
                    if (picked) onFileChange(picked)
                    event.target.value = ''
                  }}
                />
              </div>
            )}
          </div>

          <div className="submit-row">
            <button type="submit" className="primary-btn" disabled={!canSubmit}>
              <span>Провести анализ</span>
              <ArrowIcon />
            </button>
            <p className="submit-note">Демонстрационная версия — данные не сохраняются</p>
          </div>
        </form>
      </div>
    </div>
  )
}
