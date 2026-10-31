import { useRef, useState } from 'react'
import { ArrowIcon, ArrowLeftIcon, CheckIcon } from '../components/Icons'
import { EXAMPLE_TEXT, INPUT_TIPS, MAX_CHARS } from '../data'

export default function InputScreen({ text, onTextChange, onSubmit, onBack, continuing, disabled }) {
  const inputRef = useRef(null)
  const [error, setError] = useState('')
  const [reading, setReading] = useState(false)
  const readVersion = useRef(0)
  const blocked = reading || disabled

  async function readFile(file) {
    if (!file || disabled) return
    const version = ++readVersion.current
    setReading(false)
    setError('')
    if (!/\.txt$/i.test(file.name)) { setError('Поддерживается TXT в UTF-8. Текст из PDF или DOCX вставьте в поле требований.'); return }
    if (file.size > 1024 * 1024) { setError('Размер TXT должен быть не более 1 МБ.'); return }
    setReading(true)
    try {
      const content = (await file.text()).replace(/^\uFEFF/, '')
      if (version !== readVersion.current) return
      if (!content.trim()) throw new Error('Файл пуст.')
      if (content.includes('\uFFFD') || content.includes('\0')) throw new Error('Не удалось прочитать текст. Сохраните файл в кодировке UTF-8.')
      if (content.length > MAX_CHARS) throw new Error(`В файле больше ${MAX_CHARS} символов. Выберите меньший фрагмент и вставьте его вручную.`)
      onTextChange(content)
    } catch (err) { if (version === readVersion.current) setError(err.message) }
    finally { if (version === readVersion.current) setReading(false) }
  }

  return (
    <div className="flow container">
      <button type="button" className="back-btn" onClick={onBack}><ArrowLeftIcon />{continuing ? 'К переписке' : 'На главную'}</button>
      <div className="input-layout">
        <aside className="input-aside">
          <span className="eyebrow">Шаг 01</span>
          <h1 className="flow-title">{continuing ? 'Уточните требования' : 'Опишите поведение системы'}</h1>
          <p className="flow-lead">{continuing ? 'Сообщение продолжит текущий чат. Опишите уточнение или изменение правил для повторной проверки.' : 'Опишите состояния, события и ограничения. Агент построит модель и проверит её с помощью TLC.'}</p>
        </aside>
        <div className="tips"><span className="tips-title">Что стоит указать</span><ul>{INPUT_TIPS.map((tip) => <li key={tip}><CheckIcon />{tip}</li>)}</ul></div>
        <form className="form-card" onSubmit={(event) => { event.preventDefault(); if (text.trim() && !blocked) onSubmit() }}>
          <div className="field">
            <div className="field-head"><label htmlFor="plan" className="field-label">Требования к системе</label><button type="button" className="link-btn" disabled={blocked} onClick={() => onTextChange(EXAMPLE_TEXT)}>Вставить пример</button></div>
            <textarea id="plan" className="textarea" value={text} maxLength={MAX_CHARS} disabled={blocked} onChange={(event) => onTextChange(event.target.value)} placeholder="Заявку можно согласовать, отменить или исполнить. После отмены исполнение запрещено…" rows={12} required />
            <div className="field-foot"><span className="submit-note">Сообщение и ответ сохраняются в вашем чате.</span><span className="counter">{text.length.toLocaleString('ru-RU')} / {MAX_CHARS.toLocaleString('ru-RU')}</span></div>
          </div>
          <div className="field">
            <div className="dropzone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); readFile(event.dataTransfer.files?.[0]) }}>
              <span className="dropzone-text"><span>{reading ? 'Читаем файл…' : 'Импортировать требования из TXT'}</span><span className="dropzone-hint">UTF-8, до 1 МБ и 20 000 символов. Заменит текст в поле.</span></span>
              <button type="button" className="ghost-btn" disabled={blocked} onClick={() => inputRef.current?.click()}>Выбрать</button>
              <input ref={inputRef} type="file" accept=".txt,text/plain" hidden onChange={(event) => { readFile(event.target.files?.[0]); event.target.value = '' }} />
            </div>
            <p className="submit-note">Текст из PDF и DOCX можно скопировать в поле выше.</p>
            {error && <p className="error-message" role="alert">{error}</p>}
          </div>
          <div className="submit-row"><button type="submit" className="primary-btn" disabled={!text.trim() || blocked}><span>{continuing ? 'Отправить агенту' : 'Проверить требования'}</span><ArrowIcon /></button></div>
        </form>
      </div>
    </div>
  )
}
