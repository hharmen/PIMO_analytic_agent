import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const plugins = [remarkGfm]
const components = {
  table: ({ children }) => <div className="markdown-table"><table>{children}</table></div>,
}

export default function MarkdownMessage({ children }) {
  return (
    <div className="message-content markdown-content">
      <ReactMarkdown remarkPlugins={plugins} components={components} skipHtml>
        {children}
      </ReactMarkdown>
    </div>
  )
}
