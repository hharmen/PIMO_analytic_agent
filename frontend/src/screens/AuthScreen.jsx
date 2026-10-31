import { useState } from 'react'

export default function AuthScreen({ onAuthenticate, busy }) {
  const [register, setRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  return (
    <section className="flow container auth-screen">
      <h1 className="flow-title">{register ? 'Создать аккаунт' : 'Войти в PIMO'}</h1>
      <p>Сохраняйте требования, обсуждайте их с агентом и возвращайтесь к проверкам.</p>
      <form className="form-card" onSubmit={async (event) => {
        event.preventDefault()
        setError('')
        if (new TextEncoder().encode(password).length > 72) {
          setError('Пароль должен занимать не более 72 байт в UTF-8.')
          return
        }
        try { await onAuthenticate({ email: email.trim().toLowerCase(), password }, register) }
        catch (err) { setError(err.message) }
      }}>
        <label className="field-label" htmlFor="email">Email</label>
        <input className="text-input" id="email" type="email" maxLength={255} autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} disabled={busy} />
        <label className="field-label" htmlFor="password">Пароль</label>
        <input className="text-input" id="password" type="password" minLength={8} maxLength={72} autoComplete={register ? 'new-password' : 'current-password'} required value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy} />
        <p className="submit-note">От 8 символов, до 72 байт в UTF-8.</p>
        {error && <p className="error-message" role="alert">{error}</p>}
        <button className="primary-btn" type="submit" disabled={busy}>{busy ? 'Подождите…' : register ? 'Зарегистрироваться' : 'Войти'}</button>
        <button className="link-btn" type="button" disabled={busy} onClick={() => { setRegister(!register); setError('') }}>{register ? 'Уже есть аккаунт' : 'Создать аккаунт'}</button>
      </form>
    </section>
  )
}
