import { useCallback, useEffect, useRef, useState } from 'react'
import Header from './components/Header'
import Landing from './screens/Landing'
import AuthScreen from './screens/AuthScreen'
import InputScreen from './screens/InputScreen'
import AnalysisScreen from './screens/AnalysisScreen'
import ReportScreen from './screens/ReportScreen'
import ChatScreen from './screens/ChatScreen'
import ChatSidebar from './components/ChatSidebar'
import AdminScreen from './screens/AdminScreen'
import { api, downloadFile, session } from './api'
import { useHashRoute } from './hooks'
import './App.css'

const ROUTES = ['landing', 'input', 'analysis', 'chat', 'report', 'admin']
const CHAT_KEY = 'pimo.chat'
const MESSAGE_KEY = 'pimo.message'
const RECOVERY_KEY = 'pimo.session-recovery'

function readRecovery() {
  try { return JSON.parse(sessionStorage.getItem(RECOVERY_KEY)) } catch { return null }
}

export default function App() {
  const [route, navigate] = useHashRoute(ROUTES, 'landing')
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [text, setText] = useState('')
  // файл, из которого взят текст в поле: уйдёт вместе с сообщением и будет виден в истории
  const [attachedFile, setAttachedFile] = useState(null)
  const [chats, setChats] = useState([])
  const [chat, setChat] = useState(null)
  const [messages, setMessages] = useState([])
  const [checks, setChecks] = useState([])
  const [deleteId, setDeleteId] = useState(null)
  const [needsRefresh, setNeedsRefresh] = useState(false)
  const [selectedMessageId, setSelectedMessageId] = useState(null)
  const lock = useRef(false)
  const drafts = useRef({})
  const authEpoch = useRef(0)

  function updateText(nextText) {
    drafts.current[chat?.id || 'new'] = nextText
    setText(nextText)
  }

  const resetChat = useCallback(() => {
    setChat(null)
    setMessages([])
    setChecks([])
    setNeedsRefresh(false)
    setSelectedMessageId(null)
    sessionStorage.removeItem(MESSAGE_KEY)
    sessionStorage.removeItem(CHAT_KEY)
  }, [])

  const expireSession = useCallback((code) => {
    if (!session.get()) return
    const userId = user?.id || session.userId()
    const previous = readRecovery()
    const recovery = {
      userId,
      chatId: chat?.id || Number(sessionStorage.getItem(CHAT_KEY)) || previous?.chatId || null,
      text: text || (previous?.userId === userId ? previous.text : '') || '',
    }
    if (userId) sessionStorage.setItem(RECOVERY_KEY, JSON.stringify(recovery))
    else sessionStorage.removeItem(RECOVERY_KEY)
    authEpoch.current++
    session.clear()
    setUser(null); setChats([]); resetChat(); setDeleteId(null); setAttachedFile(null)
    drafts.current = {}
    lock.current = false; setBusy('')
    const message = code === 'account_blocked' ? 'Аккаунт заблокирован. Обратитесь к администратору.'
      : code === 'token_expired' ? 'Сессия истекла. Войдите снова.' : 'Сессия недействительна. Войдите снова.'
    setError(message + (recovery.text ? ' Черновик сохранён и восстановится после входа в тот же аккаунт.' : ''))
    navigate('input', { replace: true })
  }, [user, chat, text, resetChat, navigate])

  const handleError = useCallback((err) => {
    if (err.code === 'session_changed') return
    if (err.status === 401) {
      expireSession(err.code || (/истекла/i.test(err.message) ? 'token_expired' : 'invalid_token'))
    } else setError(err.message)
  }, [expireSession])

  useEffect(() => {
    if (!user) return undefined
    let active = true
    let checking = false
    let timer
    function checkExpiry() {
      const expiresAt = session.expiresAt()
      if (expiresAt === null) return false
      const remaining = expiresAt - Date.now()
      if (remaining <= 0) { expireSession('token_expired'); return true }
      window.clearTimeout(timer)
      timer = window.setTimeout(checkExpiry, Math.min(remaining, 2147483647))
      return false
    }
    async function revalidate() {
      if (document.hidden || checkExpiry() || checking) return
      checking = true
      try {
        const currentUser = await api.me()
        if (active) setUser((previous) => previous?.id === currentUser.id && previous?.is_admin === currentUser.is_admin
          && previous?.is_active === currentUser.is_active ? previous : currentUser)
      }
      catch (err) { if (active && err.status === 401) expireSession(err.code) }
      finally { checking = false }
    }
    checkExpiry()
    window.addEventListener('focus', revalidate)
    document.addEventListener('visibilitychange', revalidate)
    return () => {
      active = false
      window.clearTimeout(timer)
      window.removeEventListener('focus', revalidate)
      document.removeEventListener('visibilitychange', revalidate)
    }
  }, [user, expireSession])

  async function loadChat(selected, preserveSelection = false) {
    const [nextMessages, nextChecks] = await Promise.all([api.messages(selected.id), api.checks(selected.id)])
    setChat(selected)
    setMessages(nextMessages)
    setChecks(nextChecks)
    if (!preserveSelection) {
      setSelectedMessageId(null)
      sessionStorage.removeItem(MESSAGE_KEY)
    }
    setNeedsRefresh(false)
    sessionStorage.setItem(CHAT_KEY, String(selected.id))
  }

  useEffect(() => {
    let active = true
    const epoch = authEpoch.current
    async function restore() {
      if (!session.get()) { setReady(true); return }
      lock.current = true
      setBusy('restore')
      try {
        const currentUser = await api.me()
        if (!active || epoch !== authEpoch.current) return
        setUser(currentUser)
        const list = await api.chats()
        if (!active || epoch !== authEpoch.current) return
        setChats(list)
        const selected = list.find((item) => String(item.id) === sessionStorage.getItem(CHAT_KEY))
        if (selected) {
          const [history, runs] = await Promise.all([api.messages(selected.id), api.checks(selected.id)])
          if (!active || epoch !== authEpoch.current) return
          setChat(selected); setMessages(history); setChecks(runs)
          const messageId = Number(sessionStorage.getItem(MESSAGE_KEY))
          setSelectedMessageId(history.some((message) => message.id === messageId) ? messageId : null)
          if (route !== 'landing' && route !== 'admin') navigate(route === 'report' ? 'report' : 'chat', { replace: true })
        }
      } catch (err) { if (active && epoch === authEpoch.current) handleError(err) }
      finally {
        if (active) {
          if (epoch === authEpoch.current) { lock.current = false; setBusy('') }
          setReady(true)
        }
      }
    }
    restore()
    return () => { active = false }
    // Restore only on mount; later navigation must not reload the session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!ready || busy) return
    if (route === 'analysis') navigate(chat ? 'chat' : 'input', { replace: true })
    if ((route === 'report' || route === 'chat') && !chat) navigate('input', { replace: true })
    if (route === 'input' && chat) navigate('chat', { replace: true })
  }, [ready, busy, route, chat, navigate])

  async function action(name, work) {
    if (lock.current) return
    lock.current = true
    setBusy(name)
    setError('')
    const epoch = authEpoch.current
    try { await work() } catch (err) { if (epoch === authEpoch.current) handleError(err) }
    finally { if (epoch === authEpoch.current) { lock.current = false; setBusy('') } }
  }

  async function authenticate(credentials, register) {
    if (lock.current) return
    lock.current = true
    setBusy('auth'); setError('')
    try {
      if (register) await api.register(credentials)
      const token = await api.login(credentials)
      session.set(token.access_token)
      const currentUser = await api.me()
      const list = await api.chats()
      const recovery = readRecovery()
      resetChat()
      drafts.current = {}
      setText('')
      if (recovery?.userId === currentUser.id) {
        const selected = list.find((item) => item.id === recovery.chatId)
        if (selected) await loadChat(selected)
        setText(recovery.text || '')
        if (selected) drafts.current[selected.id] = recovery.text || ''
        navigate(selected ? 'chat' : 'input', { replace: true })
      }
      sessionStorage.removeItem(RECOVERY_KEY)
      setChats(list)
      setUser(currentUser)
    } catch (err) {
      session.clear()
      throw err
    } finally { lock.current = false; setBusy('') }
  }

  function startNew() {
    if (lock.current) return
    resetChat(); setText(''); setAttachedFile(null); setError(''); setDeleteId(null)
    navigate('input')
  }

  function logout() {
    if (lock.current) return
    session.clear(); setUser(null); setChats([]); resetChat(); setText(''); setAttachedFile(null); setError('')
    drafts.current = {}
    sessionStorage.removeItem(RECOVERY_KEY)
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
        const reply = await api.send(selected.id, text.trim(), attachedFile?.id ?? null)
        setMessages((history) => [...history, reply.user_message, reply.assistant_message])
        if (reply.check_run) setChecks((history) => [...history, reply.check_run])
        delete drafts.current[selected.id]
        setText('')
        setAttachedFile(null)
        navigate('chat', { replace: true })
        const list = await api.chats()
        setChats(list)
        setChat(list.find((item) => item.id === selected.id) || selected)
      } catch (err) {
        if (err.status === 401 || err.code === 'session_changed') throw err
        // Core saves user messages even if the agent fails. Reconcile before another send.
        setNeedsRefresh(true)
        try { await loadChat(selected) } catch (syncError) {
          if (syncError.status === 401) throw syncError
          err.message += ' Не удалось обновить историю. Нажмите «Обновить» перед продолжением.'
        }
        navigate('chat', { replace: true })
        if (err.status === 0) err.message += ' Ответ мог сохраниться на сервере. Обновите чат перед повторной отправкой.'
        throw err
      }
    })
  }

  async function importFile(file) {
    setAttachedFile(null)
    try {
      const uploaded = await api.uploadFile(file)
      setAttachedFile(uploaded)
      return uploaded
    } catch (err) {
      if (err.status === 401) handleError(err)
      throw err
    }
  }

  function openMessage(messageId) {
    if (lock.current) return
    setSelectedMessageId(messageId)
    if (messageId === null) sessionStorage.removeItem(MESSAGE_KEY)
    else sessionStorage.setItem(MESSAGE_KEY, String(messageId))
    navigate('report')
    window.scrollTo(0, 0)
  }

  function selectChat(selected) {
    if (selected.id === chat?.id) { navigate('chat'); return }
    action('load', async () => { await loadChat(selected); setText(drafts.current[selected.id] || ''); setAttachedFile(null); setDeleteId(null); navigate('chat') })
  }

  function refreshChats() {
    action('load', async () => { setChats(await api.chats()); if (chat) await loadChat(chat, true) })
  }

  function deleteChat() {
    if (deleteId !== chat.id) { setDeleteId(chat.id); return }
    action('delete', async () => {
      await api.deleteChat(chat.id)
      delete drafts.current[chat.id]
      setChats((list) => list.filter((item) => item.id !== chat.id))
      resetChat(); setText(''); setAttachedFile(null); setDeleteId(null); navigate('input')
    })
  }

  const screen = busy === 'send' ? (messages.length ? 'chat' : 'analysis') : route
  const workspace = screen !== 'landing' && screen !== 'admin' && Boolean(user)
  useEffect(() => { window.scrollTo(0, 0) }, [screen])
  return (
    <div className="app">
      <Header route={screen} onNavigate={(next) => { if (!lock.current) navigate(next) }} />
      {user && <div className="account-bar container"><span>{user.email}</span>{user.is_admin && <button className="link-btn" type="button" disabled={Boolean(busy)} onClick={() => navigate(screen === 'admin' ? (chat ? 'chat' : 'input') : 'admin')}>{screen === 'admin' ? 'К моим чатам' : 'Админ-панель'}</button>}<button className="link-btn" type="button" onClick={logout} disabled={Boolean(busy)}>Выйти</button></div>}
      {error && <div className="error-message container" role="alert">{error}</div>}
      {!ready ? <main className="flow container" role="status">Восстанавливаем сессию…</main> : <>
        <div className={workspace ? 'workspace container' : 'screen-shell'}>
        {workspace && <ChatSidebar chats={chats} currentId={chat?.id} onSelect={selectChat} onNew={startNew} onRefresh={refreshChats} disabled={Boolean(busy)} loading={busy === 'load'} />}
        <main className={`screen screen-${screen} is-enter`}>
          {busy === 'load' && <p className="workspace-loading" role="status">Загружаем историю…</p>}
          {screen === 'landing' ? <Landing onStart={() => navigate('input')} />
            : !user ? <AuthScreen onAuthenticate={authenticate} busy={Boolean(busy)} />
              : screen === 'admin' ? (user.is_admin ? <AdminScreen onAuthError={handleError} /> : <section className="flow container"><h1>Доступ запрещён</h1><p>Панель доступна только администраторам.</p><button type="button" className="ghost-btn" onClick={() => navigate(chat ? 'chat' : 'input')}>К моим чатам</button></section>)
              : screen === 'analysis' && busy === 'send' ? <AnalysisScreen />
                : screen === 'chat' && chat ? <ChatScreen chat={chat} messages={messages} checks={checks} text={text} onTextChange={updateText} onSubmit={send} onImportFile={importFile} attachedFile={attachedFile} onDetachFile={() => setAttachedFile(null)} onOpenMessage={openMessage} onOpenChecks={() => openMessage(null)} onRefresh={refreshChats} onDelete={deleteChat} deletePending={deleteId === chat.id} onCancelDelete={() => setDeleteId(null)} disabled={Boolean(busy)} sending={busy === 'send'} needsRefresh={needsRefresh} loading={busy === 'load'} />
                  : screen === 'report' && chat ? <ReportScreen chat={chat} messages={messages} checks={checks} selectedMessageId={selectedMessageId} onDownloadFile={(file) => action('download', () => downloadFile(file.id, file.filename))} onBack={() => navigate('chat')} disabled={Boolean(busy)} />
                    : <InputScreen disabled={Boolean(busy) || needsRefresh} text={text} onTextChange={setText} onSubmit={send} onImportFile={importFile} attachedFile={attachedFile} onDetachFile={() => setAttachedFile(null)} continuing={Boolean(chat)} onBack={() => { if (!lock.current) navigate(chat ? 'chat' : 'landing') }} />}
        </main>
        </div>
      </>}
      <footer className="footer container"><span>PIMO · агент-аналитик</span><span>Проверка конечной модели требований с помощью TLC</span></footer>
    </div>
  )
}
