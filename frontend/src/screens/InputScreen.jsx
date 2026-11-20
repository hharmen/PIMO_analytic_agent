import { useRef } from 'react'
import { ArrowIcon, ArrowLeftIcon, CheckIcon } from '../components/Icons'
import { EXAMPLE_TEXT, FILE_TYPES, INPUT_TIPS, MAX_CHARS, MAX_FILE_MB } from '../data'
import { useFileImport } from '../fileImport'
import FileWarnings from '../components/FileWarnings'

export default function InputScreen({ text, onTextChange, onSubmit, onBack, onImportFile, attachedFile, onDetachFile, continuing, disabled }) {
  const inputRef = useRef(null)
  const { readFile, reading, error } = useFileImport({ onImportFile, onTextChange, onDetachFile, disabled })
  const blocked = reading || disabled

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
            <div className="field-head"><label htmlFor="plan" className="field-label">Требования к системе</label><button type="button" className="link-btn" disabled={blocked} onClick={() => { onTextChange(EXAMPLE_TEXT); onDetachFile() }}>Вставить пример</button></div>
            <textarea id="plan" className="textarea" value={text} maxLength={MAX_CHARS} disabled={blocked} onChange={(event) => onTextChange(event.target.value)} placeholder="Заявку можно согласовать, отменить или исполнить. После отмены исполнение запрещено…" rows={12} required />
            <div className="field-foot"><span className="submit-note">Сообщение и ответ сохраняются в вашем чате.</span><span className="counter">{text.length.toLocaleString('ru-RU')} / {MAX_CHARS.toLocaleString('ru-RU')}</span></div>
          </div>
          <div className="field">
            <div className="dropzone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); readFile(event.dataTransfer.files?.[0]) }}>
              <span className="dropzone-text"><span>{reading ? 'Извлекаем текст…' : 'Импортировать требования из файла'}</span><span className="dropzone-hint">TXT, MD, DOCX, PDF или картинка PNG/JPG, до {MAX_FILE_MB} МБ и {MAX_CHARS.toLocaleString('ru-RU')} символов. Заменит текст в поле.</span></span>
              <button type="button" className="ghost-btn" disabled={blocked} onClick={() => inputRef.current?.click()}>Выбрать</button>
              <input ref={inputRef} type="file" accept={FILE_TYPES.join(',')} hidden onChange={(event) => { readFile(event.target.files?.[0]); event.target.value = '' }} />
            </div>
            <p className="submit-note">Сканы и картинки распознаются автоматически (OCR) — это может занять до минуты.</p>
            {attachedFile && <p className="submit-note" role="status">Текст из «{attachedFile.filename}» вставлен в поле: {attachedFile.chars.toLocaleString('ru-RU')} символов. Проверьте его перед отправкой: файл сохранится в истории чата. <button type="button" className="link-btn" disabled={blocked} onClick={onDetachFile}>Открепить файл</button></p>}
            <FileWarnings file={attachedFile} />
            {error && <p className="error-message" role="alert">{error}</p>}
          </div>
          <div className="submit-row"><button type="submit" className="primary-btn" disabled={!text.trim() || blocked}><span>{continuing ? 'Отправить агенту' : 'Проверить требования'}</span><ArrowIcon /></button></div>
        </form>
      </div>
    </div>
  )
}
