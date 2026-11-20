// Доступ к агенту (срок и лимит в сутки выдаёт админ). Данные - из /auth/me (agent_access).
// Сервер всё равно проверяет сам; здесь - чтобы заранее показать причину и не создавать пустой чат.

// последний день доступа по Москве: access_until - это 00:00 МСК следующего дня
export function accessDate(accessUntil) {
  if (!accessUntil) return ''
  return new Date(Date.parse(accessUntil) - 1000).toLocaleDateString('ru-RU', { timeZone: 'Europe/Moscow' })
}

// Почему нельзя отправить запрос агенту; пустая строка - можно
export function accessProblem(access) {
  if (!access) return ''
  if (access.state === 'none') return 'Доступ к агенту ещё не выдан. Обратитесь к администратору.'
  if (access.state === 'expired') return `Доступ к агенту закончился ${accessDate(access.access_until)}. Обратитесь к администратору.`
  if (access.state === 'limit_reached') return `Лимит ${access.daily_limit} запросов на сегодня исчерпан. Новые запросы — после 00:00 МСК.`
  return ''
}

// Короткая строка для панели аккаунта
export function accessLabel(access) {
  if (!access || access.state === 'unlimited') return ''
  if (access.state === 'none') return 'Доступ к агенту не выдан'
  if (access.state === 'expired') return `Доступ закончился ${accessDate(access.access_until)}`
  const limit = access.daily_limit ? `сегодня ${access.used_today} из ${access.daily_limit}` : 'без лимита запросов'
  return `Доступ до ${accessDate(access.access_until)} · ${limit}`
}
