const API_URL = (import.meta.env?.VITE_API_URL || '/api').replace(/\/$/, '')
const TOKEN_KEY = 'pimo.token'

export const session = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

export async function request(path, { method = 'GET', body, token = session.get() } = {}) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })
  } catch {
    throw new ApiError('Не удалось связаться с Core API. Проверьте соединение и доступность сервера.', 0)
  }
  if (response.status === 204) return null
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data?.detail
    const message = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map((issue) => `${issue.loc?.at(-1) || 'Данные'}: ${issue.msg}`).join('; ')
        : `Ошибка сервера (${response.status}). Попробуйте позже.`
    throw new ApiError(message, response.status)
  }
  if (data === null) throw new ApiError('Сервер вернул некорректный ответ. Проверьте адрес Core API.', response.status)
  return data
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
