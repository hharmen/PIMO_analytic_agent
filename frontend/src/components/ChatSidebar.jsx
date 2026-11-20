import { useState } from 'react'
import { chatTitle } from '../data'
import { DocIcon } from './Icons'

export default function ChatSidebar({ chats, currentId, onSelect, onNew, onRefresh, disabled, loading }) {
  const [search, setSearch] = useState('')
  const visible = chats.filter((chat) => chat.title.toLocaleLowerCase('ru').includes(search.toLocaleLowerCase('ru').trim()))
  return <aside className="chat-sidebar" aria-label="Ваши чаты">
    <div className="sidebar-heading"><h2>Мои чаты <span>{chats.length}</span></h2><button type="button" className="link-btn" onClick={onRefresh} disabled={disabled} aria-label="Обновить чаты">Обновить</button></div>
    <button type="button" className="primary-btn new-chat-btn" onClick={onNew} disabled={disabled}><span aria-hidden="true">＋</span> Новый чат</button>
    <label className="sr-only" htmlFor="chat-search">Поиск чатов</label>
    <input id="chat-search" className="chat-search" type="search" placeholder="Найти чат…" value={search} onChange={(event) => setSearch(event.target.value)} />
    <nav className="chat-list" aria-label="Список чатов" aria-busy={loading}>
      {visible.map((chat) => <button type="button" key={chat.id} className={`chat-list-item ${chat.id === currentId ? 'is-active' : ''}`} aria-current={chat.id === currentId ? 'page' : undefined} onClick={() => onSelect(chat)} disabled={disabled}>
        <span className="chat-list-icon"><DocIcon /></span><span className="chat-list-copy"><strong>{chatTitle(chat.title)}</strong><time dateTime={chat.created_at}>{new Date(chat.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}</time></span>
      </button>)}
      {!visible.length && <p className="sidebar-empty">{search.trim() ? 'Чаты не найдены.' : 'Здесь появятся ваши диалоги с агентом.'}</p>}
    </nav>
    <p className="sidebar-note">Каждый чат — отдельный анализ. Вся переписка сохраняется.</p>
  </aside>
}
