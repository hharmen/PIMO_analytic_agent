import { useEffect, useRef, useState } from 'react'
import Header from './components/Header'
import Landing from './screens/Landing'
import AuthScreen from './screens/AuthScreen'
import InputScreen from './screens/InputScreen'
import AnalysisScreen from './screens/AnalysisScreen'
import ReportScreen from './screens/ReportScreen'
import { api, session } from './api'
import { useHashRoute } from './hooks'
import './App.css'

const ROUTES = ['landing', 'input', 'analysis', 'report']
const CHAT_KEY = 'pimo.chat'

export default function App() {
  const [route, navigate] = useHashRoute(ROUTES, 'landing')
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [text, setText] = useState('')
  const [chats, setChats] = useState([])
  const [chat, setChat] = useState(null)
  const [messages, setMessages] = useState([])
  const [checks, setChecks] = useState([])
  const [deleteId, setDeleteId] = useState(null)
  const [needsRefresh, setNeedsRefresh] = useState(false)
  const lock = useRef(false)

  function resetChat() {
    setChat(null)
    setMessages([])
    setChecks([])
    setNeedsRefresh(false)
    sessionStorage.removeItem(CHAT_KEY)
  }

  function handleError(err) {
    if (err.status === 401) {
      session.clear()
      sessionStorage.removeItem(CHAT_KEY)
      setUser(null)
      setChats([])
      resetChat()
      setError('Сессия истекла. Войдите снова; текст в поле сохранён.')
    } else setError(err.message)
  }

  async function loadChat(selected) {
    const [nextMessages, nextChecks] = await Promise.all([api.messages(selected.id), api.checks(selected.id)])
    setChat(selected)
    setMessages(nextMessages)
    setChecks(nextChecks)
    setNeedsRefresh(false)
    sessionStorage.setItem(CHAT_KEY, String(selected.id))
  }

  useEffect(() => {
    let active = true
    async function restore() {
      if (!session.get()) { setReady(true); return }
      lock.current = true
      setBusy('restore')
      try {
        const currentUser = await api.me()
        if (!active) return
        setUser(currentUser)
        const list = await api.chats()
        if (!active) return
        setChats(list)
        const selected = list.find((item) => String(item.id) === sessionStorage.getItem(CHAT_KEY))
        if (selected) {
          const [history, runs] = await Promise.all([api.messages(selected.id), api.checks(selected.id)])
          if (!active) return
          setChat(selected); setMessages(history); setChecks(runs)
          if (route !== 'landing') navigate('report', { replace: true })
        }
      } catch (err) { if (active) handleError(err) }
      finally { if (active) { lock.current = false; setBusy(''); setReady(true) } }
    }
    restore()
    return () => { active = false }
    // Restore only on mount; later navigation must not reload the session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!ready || busy) return
    if (route === 'analysis') navigate(chat ? 'report' : 'input', { replace: true })
    if (route === 'report' && !chat) navigate('input', { replace: true })
  }, [ready, busy, route, chat, navigate])

  async function action(name, work) {
    if (lock.current) return
    lock.current = true
    setBusy(name)
    setError('')
    try { await work() } catch (err) { handleError(err) }
    finally { lock.current = false; setBusy('') }
  }

  async function authenticate(credentials, register) {
    if (lock.current) return
    lock.current = true
    setBusy('auth'); setError('')
    try {
      if (register) await api.register(credentials)
      const token = await api.login(credentials)
      session.set(token.access_token)
      setUser(await api.me())
      try { setChats(await api.chats()) } catch (err) { handleError(err) }
    } finally { lock.current = false; setBusy('') }
  }

  function startNew() {
    if (lock.current) return
    resetChat(); setText(''); setError(''); setDeleteId(null)
    navigate('input')
  }

  function logout() {
    if (lock.current) return
    session.clear(); setUser(null); setChats([]); resetChat(); setText(''); setError('')
    navigate('landing')
  }

  async function send() {
    if (!text.trim() || lock.current || needsRefresh) return
    await action('send', async () => {
      let selected = chat
      if (!selected) {
        selected = await api.createChat()
        setChat(selected)
        setChats((list) => [selected, ...list])
        sessionStorage.setItem(CHAT_KEY, String(selected.id))
      }
      navigate('analysis')
      try {
        const reply = await api.send(selected.id, text.trim())
        setMessages((history) => [...history, reply.user_message, reply.assistant_message])
        if (reply.check_run) setChecks((history) => [...history, reply.check_run])
        setText('')
        navigate('report', { replace: true })
        const list = await api.chats()
        setChats(list)
        setChat(list.find((item) => item.id === selected.id) || selected)
      } catch (err) {
        // Core saves user messages even if the agent fails. Reconcile before another send.
        setNeedsRefresh(true)
        try { await loadChat(selected) } catch (syncError) {
          if (syncError.status === 401) throw syncError
          err.message += ' Не удалось обновить историю. Нажмите «Обновить» перед продолжением.'
        }
        navigate('report', { replace: true })
        if (err.status === 0) err.message += ' Ответ мог сохраниться на сервере. Обновите чат перед повторной отправкой.'
        throw err
      }
    })
  }

  const screen = busy === 'send' ? 'analysis' : route
  return (
    <div className="app">
      <Header route={screen} onNavigate={(next) => { if (!lock.current) navigate(next) }} />
      {user && <div className="account-bar container"><span>{user.email}</span><button className="link-btn" type="button" onClick={logout} disabled={Boolean(busy)}>Выйти</button></div>}
      {error && <div className="error-message container" role="alert">{error}</div>}
      {!ready ? <main className="flow container" role="status">Восстанавливаем сессию…</main> : <>
        {screen !== 'landing' && user && <nav className="chat-bar container" aria-label="Чаты">
          <button type="button" className="ghost-btn" disabled={Boolean(busy)} onClick={startNew}>Новый чат</button>
          <label htmlFor="chat-select">История</label>
          <select id="chat-select" value={chat?.id || ''} disabled={Boolean(busy)} onChange={(event) => {
            const selected = chats.find((item) => item.id === Number(event.target.value))
            if (selected) action('load', async () => { await loadChat(selected); setText(''); setDeleteId(null); navigate('report') })
          }}><option value="" disabled>Выберите чат</option>{chats.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select>
          <button type="button" className="link-btn" disabled={Boolean(busy)} onClick={() => action('load', async () => { setChats(await api.chats()); if (chat) await loadChat(chat) })}>Обновить</button>
          {chat && (deleteId === chat.id ? <>
            <span>Удалить чат и его историю?</span>
            <button className="link-btn" type="button" disabled={Boolean(busy)} onClick={() => action('delete', async () => { await api.deleteChat(chat.id); setChats((list) => list.filter((item) => item.id !== chat.id)); resetChat(); setText(''); setDeleteId(null); navigate('input') })}>Да, удалить</button>
            <button className="link-btn" type="button" disabled={Boolean(busy)} onClick={() => setDeleteId(null)}>Отмена</button>
          </> : <button className="link-btn" type="button" disabled={Boolean(busy)} onClick={() => setDeleteId(chat.id)}>Удалить чат</button>)}
          {busy && busy !== 'send' && <span role="status">Загрузка…</span>}
        </nav>}
        <main className={`screen screen-${screen} is-enter`}>
          {screen === 'landing' ? <Landing onStart={() => navigate('input')} />
            : !user ? <AuthScreen onAuthenticate={authenticate} busy={Boolean(busy)} />
              : screen === 'analysis' && busy === 'send' ? <AnalysisScreen />
                : screen === 'report' && chat ? <ReportScreen chat={chat} messages={messages} checks={checks} onEdit={() => { if (!lock.current) navigate('input') }} onRestart={startNew} disabled={Boolean(busy) || needsRefresh} />
                  : <InputScreen disabled={Boolean(busy) || needsRefresh} text={text} onTextChange={setText} onSubmit={send} continuing={Boolean(chat)} onBack={() => { if (!lock.current) navigate(chat ? 'report' : 'landing') }} />}
        </main>
      </>}
      <footer className="footer container"><span>PIMO · агент-аналитик</span><span>Проверка конечной модели требований с помощью TLC</span></footer>
    </div>
  )
}
