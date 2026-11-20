// Предупреждения File Service: какие страницы распознаны OCR или не попали в текст
export default function FileWarnings({ file }) {
  if (!file?.warnings?.length) return null
  return <ul className="file-warnings" role="status">{file.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
}
