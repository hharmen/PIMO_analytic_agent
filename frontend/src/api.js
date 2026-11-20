const API_URL = (import.meta.env?.VITE_API_URL || '/api').replace(/\/$/, '')
const TOKEN_KEY = 'pimo.token'
const activeRequests = new Set()
let sessionVersion = 0

// These claims only drive the interface timer. Authorization is always checked
// on the server, including the signature and whether the user still exists.
function tokenClaims(token) {
  try {
    const parts = token?.split('.')
    if (parts?.length !== 3) return null
    return JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
  } catch { return null }
}

export const session = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token) => { sessionVersion++; sessionStorage.setItem(TOKEN_KEY, token) },
  clear: () => {
    sessionVersion++
    sessionStorage.removeItem(TOKEN_KEY)
    for (const controller of activeRequests) controller.abort()
  },
  expiresAt: () => {
    const exp = tokenClaims(session.get())?.exp
    return typeof exp === 'number' && Number.isFinite(exp * 1000) ? exp * 1000 : null
  },
  userId: () => {
    const subject = tokenClaims(session.get())?.sub
    const id = typeof subject === 'string' && /^\d+$/.test(subject) ? Number(subject) : NaN
    return Number.isSafeInteger(id) && id > 0 ? id : null
  },
}

export class ApiError extends Error {
  constructor(message, status, code = '') {
    super(message)
    this.status = status
    this.code = code
  }
}

export async function request(path, { method = 'GET', body, token = session.get() } = {}) {
  const version = sessionVersion
  const controller = new AbortController()
  if (token) activeRequests.add(controller)
  const assertCurrentSession = () => {
    if (token && (token !== session.get() || version !== sessionVersion)) throw new ApiError('Сессия изменилась.', 0, 'session_changed')
  }
  try {
    let response
    try {
      response = await fetch(`${API_URL}${path}`, {
        method,
        signal: controller.signal,
        headers: {
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      })
    } catch {
      assertCurrentSession()
      throw new ApiError('Не удалось связаться с Core API. Проверьте соединение и доступность сервера.', 0)
    }
    assertCurrentSession()
    if (response.status === 204) return null
    const data = await response.json().catch(() => null)
    assertCurrentSession()
    if (!response.ok) {
      const detail = data?.detail
      const message = typeof detail === 'string' ? detail
        : Array.isArray(detail) ? detail.map((issue) => `${issue.loc?.at(-1) || 'Данные'}: ${issue.msg}`).join('; ')
          : typeof detail?.message === 'string' ? detail.message
          : `Ошибка сервера (${response.status}). Попробуйте позже.`
      throw new ApiError(message, response.status, typeof detail?.code === 'string' ? detail.code : '')
    }
    if (data === null) throw new ApiError('Сервер вернул некорректный ответ. Проверьте адрес Core API.', response.status)
    return data
  } finally { activeRequests.delete(controller) }
}

export const api = {
  me: () => request('/auth/me'),
  register: (body) => request('/auth/register', { method: 'POST', body, token: null }),
  login: (body) => request('/auth/login', { method: 'POST', body, token: null }),
  chats: () => request('/chats'),
  createChat: () => request('/chats', { method: 'POST', body: {} }),
  deleteChat: (id) => request(`/chats/${id}`, { method: 'DELETE' }),
  messages: (id) => request(`/chats/${id}/messages`),
  checks: (id) => request(`/chats/${id}/checks`),
  send: (id, content) => request(`/chats/${id}/messages`, { method: 'POST', body: { content } }),
}
