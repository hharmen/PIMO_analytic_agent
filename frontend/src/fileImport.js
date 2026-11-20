import { useRef, useState } from 'react'
import { FILE_TYPES, MAX_CHARS, MAX_FILE_MB } from './data'

// Импорт требований из файла: общий для первого экрана и поля ввода в переписке.
// Текст извлекает File Service (сканы и картинки - через OCR), файл сохраняется на сервере
// и уходит вместе с сообщением.
export function useFileImport({ onImportFile, onTextChange, onDetachFile, disabled }) {
  const [error, setError] = useState('')
  const [reading, setReading] = useState(false)
  const readVersion = useRef(0)

  async function readFile(file) {
    if (!file || disabled) return
    const version = ++readVersion.current
    setReading(false)
    setError('')
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    if (!FILE_TYPES.includes(ext)) { setError('Поддерживаются файлы TXT, MD, DOCX, PDF и картинки PNG, JPG.'); return }
    if (file.size > MAX_FILE_MB * 1024 * 1024) { setError(`Размер файла должен быть не более ${MAX_FILE_MB} МБ.`); return }
    setReading(true)
    try {
      const uploaded = await onImportFile(file)
      if (version !== readVersion.current) return
      if (uploaded.text.length > MAX_CHARS) { onDetachFile(); throw new Error(`В файле больше ${MAX_CHARS} символов. Оставьте в нём только описание поведения системы.`) }
      onTextChange(uploaded.text)
    } catch (err) {
      // 401 обрабатывает App (выход и сообщение о сессии), здесь не дублируем
      if (version === readVersion.current && err.status !== 401 && err.code !== 'session_changed') setError(err.message)
    } finally { if (version === readVersion.current) setReading(false) }
  }

  return { readFile, reading, error }
}
