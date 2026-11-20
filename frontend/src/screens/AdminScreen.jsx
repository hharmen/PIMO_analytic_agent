import { useEffect, useState } from 'react'
import { adminApi } from '../api'
import { statusLabel } from '../data'

const PAGE_SIZE = 25
const AUDIT_SIZE = 20
const dateLabel = (value) => value ? new Date(value).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : 'Нет сообщений'
const actionLabel = { block_user: 'Блокировка', unblock_user: 'Разблокировка', grant_admin: 'Назначение администратора', revoke_admin: 'Снятие роли администратора' }

function Pagination({ total, offset, limit, onChange, disabled, label }) {
  return <nav className="admin-pagination" aria-label={label}>
    <span>{total ? `${offset + 1}–${Math.min(offset + limit, total)} из ${total}` : 'Нет записей'}</span>
    <button type="button" className="ghost-btn" aria-label={`${label}: назад`} disabled={disabled || offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Назад</button>
    <button type="button" className="ghost-btn" aria-label={`${label}: далее`} disabled={disabled || offset + limit >= total} onClick={() => onChange(offset + limit)}>Далее</button>
  </nav>
}

export default function AdminScreen({ onAuthError }) {
  const [searchText, setSearchText] = useState('')
  const [search, setSearch] = useState('')
  const [state, setState] = useState('all')
  const [offset, setOffset] = useState(0)
  const [auditOffset, setAuditOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [denied, setDenied] = useState(false)
  const disabled = loading || saving !== null

  useEffect(() => {
    let active = true
    async function load() {
      setLoading(true); setError('')
      try {
        const [summary, users, audit] = await Promise.all([
          adminApi.summary(), adminApi.users({ q: search, state, limit: PAGE_SIZE, offset }),
          adminApi.audit({ limit: AUDIT_SIZE, offset: auditOffset }),
        ])
        if (!active) return
        if (offset > 0 && offset >= users.total) { setOffset(Math.max(0, Math.ceil(users.total / PAGE_SIZE) - 1) * PAGE_SIZE); return }
        if (auditOffset > 0 && auditOffset >= audit.total) { setAuditOffset(Math.max(0, Math.ceil(audit.total / AUDIT_SIZE) - 1) * AUDIT_SIZE); return }
        setData({ summary, users, audit })
      } catch (err) {
        if (!active || err.code === 'session_changed') return
        setData(null)
        if (err.status === 401) onAuthError(err)
        else if (err.status === 403) setDenied(true)
        else setError(err.message)
      } finally { if (active) setLoading(false) }
    }
    load()
    return () => { active = false }
  }, [search, state, offset, auditOffset, revision, onAuthError])

  async function changeStatus(user) {
    if (disabled || user.is_admin) return
    const message = user.is_active
      ? `Заблокировать ${user.email}? Пользователь потеряет доступ к аккаунту. Чаты сохранятся.`
      : `Разблокировать ${user.email}? Пользователь снова сможет войти.`
    if (!window.confirm(message)) return
    setSaving(user.id); setError(''); setNotice('')
    try {
      await adminApi.setActive(user.id, !user.is_active)
      setNotice(`Аккаунт ${user.email} ${user.is_active ? 'заблокирован' : 'разблокирован'}.`)
      setRevision((value) => value + 1)
    } catch (err) {
      if (err.code === 'session_changed') return
      if (err.status === 401) onAuthError(err)
      else if (err.status === 403) { setDenied(true); setData(null) }
      else setError(err.message)
    } finally { setSaving(null) }
  }

  if (denied) return <section className="flow container"><h1>Доступ запрещён</h1><p>Права администратора отозваны. Вернитесь к своим чатам.</p></section>

  return <div className="flow container admin-screen">
    <div className="admin-heading"><div><span className="eyebrow">Управление PIMO</span><h1>Админ-панель</h1><p>Пользователи, активность и результаты проверок</p></div><button type="button" className="ghost-btn" disabled={disabled} onClick={() => setRevision((value) => value + 1)}>Обновить данные</button></div>
    {error && <p className="error-message" role="alert">{error} <button type="button" className="link-btn" disabled={disabled} onClick={() => setRevision((value) => value + 1)}>Повторить</button></p>}
    {notice && <p className="admin-notice" role="status">{notice}</p>}
    {loading && <p role="status" className="submit-note">Загружаем данные панели…</p>}
    {data && <>
      <section className="admin-metrics" aria-label="Статистика приложения">
        <article><span>Пользователи</span><strong>{data.summary.users}</strong><small>{data.summary.admins} администраторов</small></article>
        <article><span>Заблокированы</span><strong>{data.summary.blocked_users}</strong><small>{data.summary.active_users} активных аккаунтов</small></article>
        <article><span>Чаты</span><strong>{data.summary.chats}</strong><small>{data.summary.messages} сообщений</small></article>
        <article><span>Проверки</span><strong>{data.summary.checks}</strong><small>{data.summary.checks_by_status.PROPERTY_VIOLATED || 0} с нарушениями</small></article>
      </section>
      <section className="admin-section" aria-labelledby="admin-users-title" aria-busy={loading}>
        <div className="admin-section-heading"><div><h2 id="admin-users-title">Пользователи</h2><p>Блокировка запрещает вход и новые запросы, сохраняя историю.</p></div><span>{data.users.total} найдено</span></div>
        <form className="admin-filters" onSubmit={(event) => { event.preventDefault(); setSearch(searchText.trim()); setOffset(0) }}>
          <label>Поиск по email<input type="search" placeholder="name@example.com" value={searchText} maxLength={255} onChange={(event) => setSearchText(event.target.value)} /></label>
          <button type="submit" className="ghost-btn" disabled={disabled}>Найти</button>
          <label>Статус аккаунта<select value={state} disabled={disabled} onChange={(event) => { setState(event.target.value); setOffset(0) }}><option value="all">Все</option><option value="active">Активные</option><option value="blocked">Заблокированные</option></select></label>
        </form>
        <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>Пользователь</th><th>Роль / статус</th><th>Регистрация</th><th>Чаты / сообщения / проверки</th><th>Последнее сообщение</th><th>Действие</th></tr></thead><tbody>
          {data.users.items.map((user) => <tr key={user.id}><td><strong>{user.email}</strong><small>ID {user.id}</small></td><td><span className="admin-role">{user.is_admin ? 'Администратор' : 'Пользователь'}</span><span className={`account-status ${user.is_active ? 'is-active' : 'is-blocked'}`}>{user.is_active ? 'Активен' : 'Заблокирован'}</span></td><td>{dateLabel(user.created_at)}</td><td><span className="admin-counts" aria-label={`${user.chat_count} чатов, ${user.message_count} сообщений, ${user.check_count} проверок`}>{user.chat_count} / {user.message_count} / {user.check_count}</span></td><td>{dateLabel(user.last_activity_at)}</td><td>{user.is_admin ? <span className="submit-note">Защищённый аккаунт</span> : <button type="button" className="link-btn" disabled={disabled} onClick={() => changeStatus(user)} aria-label={`${user.is_active ? 'Заблокировать' : 'Разблокировать'} ${user.email}`}>{saving === user.id ? 'Сохраняем…' : user.is_active ? 'Заблокировать' : 'Разблокировать'}</button>}</td></tr>)}
        </tbody></table></div>
        {!data.users.items.length && <p className="empty-state">Пользователи не найдены. Измените поиск или фильтр.</p>}
        <Pagination label="Страницы пользователей" total={data.users.total} offset={offset} limit={PAGE_SIZE} onChange={setOffset} disabled={disabled} />
      </section>
      <section className="admin-section" aria-label="Статусы проверок"><h2>Результаты проверок</h2><div className="admin-check-statuses">{Object.entries(data.summary.checks_by_status).map(([status, count]) => <div key={status}><span className={`result-badge status-${status}`}>{statusLabel(status)}</span><strong>{count}</strong></div>)}</div>{!data.summary.checks && <p className="submit-note">Проверок пока нет.</p>}</section>
      <section className="admin-section" aria-labelledby="admin-audit-title"><div className="admin-section-heading"><div><h2 id="admin-audit-title">Журнал действий</h2><p>Кто изменил доступ и когда</p></div><span>{data.audit.total} записей</span></div>
        <div className="admin-table-scroll"><table className="admin-table audit-table"><thead><tr><th>Когда</th><th>Кто</th><th>Действие</th><th>Аккаунт</th></tr></thead><tbody>{data.audit.items.map((item) => <tr key={item.id}><td>{dateLabel(item.created_at)}</td><td>{item.actor_email === 'server-cli' ? 'Серверная команда' : item.actor_email}</td><td>{actionLabel[item.action] || item.action}</td><td>{item.target_email}</td></tr>)}</tbody></table></div>
        {!data.audit.items.length && <p className="submit-note">Изменений доступа пока нет.</p>}
        <Pagination label="Страницы журнала" total={data.audit.total} offset={auditOffset} limit={AUDIT_SIZE} onChange={setAuditOffset} disabled={disabled} />
      </section>
    </>}
  </div>
}
