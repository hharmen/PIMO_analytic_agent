import { useEffect, useRef } from 'react'
import { ArrowIcon } from '../components/Icons'
import { chatTitle, FILE_TYPES, MAX_CHARS, statusLabel } from '../data'
import { checksForMessage, messagePreview } from '../conversation'
import { useFileImport } from '../fileImport'
import FileWarnings from '../components/FileWarnings'

export default function ChatScreen({ chat, messages, checks, text, onTextChange, onSubmit, onImportFile, attachedFile, onDetachFile, onOpenMessage, onOpenChecks, onRefresh, onDelete, deletePending, onCancelDelete, disabled, sending, needsRefresh, loading }) {
  const timelineRef = useRef(null)
  const fileRef = useRef(null)
  const { readFile, reading, error } = useFileImport({ onImportFile, onTextChange, onDetachFile, disabled: disabled || needsRefresh })
  const blocked = disabled || needsRefresh || reading
  useEffect(() => {
    const timeline = timelineRef.current
    if (timeline) timeline.scrollTop = timeline.scrollHeight
  }, [chat.id, messages.length, sending])

  return <div className="messenger">
    <header className="messenger-heading">
      <div><span className="eyebrow">Диалог с агентом</span><h1>{chatTitle(chat.title)}</h1><p>{messages.length} сообщений · {checks.length} проверок</p></div>
      <div className="chat-actions"><button type="button" className="link-btn" disabled={disabled} onClick={onOpenChecks}>Все проверки</button><button type="button" className="link-btn" disabled={disabled} onClick={onDelete}>Удалить чат</button></div>
    </header>
    {deletePending && <div className="delete-confirm" role="alert"><span>Удалить чат и его историю?</span><button type="button" className="link-btn" disabled={disabled} onClick={onDelete}>Да, удалить</button><button type="button" className="link-btn" disabled={disabled} onClick={onCancelDelete}>Отмена</button></div>}
    <section ref={timelineRef} aria-label="Переписка" className="message-timeline" aria-busy={loading}>
      {!messages.length && !sending && <p className="empty-state">В этом чате ещё нет сообщений. Добавьте требования для проверки.</p>}
      {messages.map((message) => {
        const runs = checksForMessage(messages, checks, message.id)
        return <article key={message.id} className={`message-preview message-preview-${message.role}`}>
          <div className="message-heading"><strong>{message.role === 'user' ? 'Вы' : 'Агент-аналитик'}</strong><time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</time></div>
          <button type="button" className="message-preview-button" onClick={() => onOpenMessage(message.id)} disabled={disabled} aria-label={`Открыть ${message.role === 'assistant' ? 'ответ агента' : 'сообщение'}: ${messagePreview(message.content).slice(0, 80)}`}>
            {message.file && <span className="message-file">Из файла «{message.file.filename}»</span>}
            <span className="message-excerpt">{messagePreview(message.content)}</span>
            <span className="message-preview-footer">{runs.length > 0 && <span className={`result-badge status-${runs.at(-1).status}`}>{statusLabel(runs.at(-1).status)}</span>}<span className="open-message">{message.role === 'assistant' ? 'Открыть ответ' : 'Читать полностью'} <ArrowIcon /></span></span>
          </button>
        </article>
      })}
      {sending && <><article className="message-preview message-preview-user pending-message"><div className="message-heading"><strong>Вы</strong><span>Отправляется…</span></div>{attachedFile && <p className="message-file">Из файла «{attachedFile.filename}»</p>}<p className="message-excerpt">{messagePreview(text)}</p></article><div className="agent-typing" role="status"><span className="typing-dots" aria-hidden="true">● ● ●</span> Агент анализирует требования…</div></>}
    </section>
    <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); if (text.trim() && !disabled && !needsRefresh) onSubmit() }}>
      {needsRefresh && <p className="composer-note">Обновите историю перед отправкой. <button type="button" className="link-btn" disabled={disabled} onClick={onRefresh}>Обновить</button></p>}
      <label htmlFor="chat-message">Продолжить диалог</label>
      <div className="composer-input"><textarea id="chat-message" value={text} maxLength={MAX_CHARS} rows={3} disabled={blocked} onChange={(event) => onTextChange(event.target.value)} placeholder="Уточните требования или задайте вопрос агенту…" onKeyDown={(event) => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form.requestSubmit() } }} /><button type="submit" className="primary-btn" aria-label="Отправить агенту" disabled={!text.trim() || blocked}><span>Отправить</span><ArrowIcon /></button></div>
      {attachedFile && <p className="composer-note" role="status">Текст из «{attachedFile.filename}» вставлен в поле, файл сохранится в истории чата. <button type="button" className="link-btn" disabled={blocked} onClick={onDetachFile}>Открепить файл</button></p>}
      <FileWarnings file={attachedFile} />
      {error && <p className="error-message" role="alert">{error}</p>}
      <p className="composer-note">
        <button type="button" className="link-btn" disabled={blocked} onClick={() => fileRef.current?.click()}>{reading ? 'Извлекаем текст…' : 'Прикрепить файл'}</button>
        <input ref={fileRef} type="file" accept={FILE_TYPES.join(',')} hidden onChange={(event) => { readFile(event.target.files?.[0]); event.target.value = '' }} />
        {' '}TXT, MD, DOCX, PDF, PNG, JPG · Ctrl + Enter — отправить · {text.length.toLocaleString('ru-RU')} / {MAX_CHARS.toLocaleString('ru-RU')}
      </p>
    </form>
  </div>
}
