import { test, expect } from '@playwright/test'

const date = '2026-11-20T16:00:00Z'
const makeUser = (id) => ({
  id, email: id === 1 ? 'admin@example.com' : `user${id}@example.com`, created_at: date,
  is_admin: id === 1, is_active: true, chat_count: id === 1 ? 0 : 2,
  message_count: 4, check_count: 1, last_activity_at: date,
})

async function setup(page, { admin = true, failLoad = false, route = 'admin' } = {}) {
  const state = { admin, failLoad, expired: false, authCode: 'token_expired', adminRequests: 0, patches: 0,
    users: Array.from({ length: 28 }, (_, index) => makeUser(index + 1)), audit: [] }
  await page.addInitScript(() => {
    sessionStorage.setItem('pimo.token', 'test-admin-token')
    sessionStorage.setItem('pimo.chat', '77')
  })
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace('/api', '')
    const reply = (json, status = 200) => route.fulfill({ status, json })
    if (state.expired) return reply({ detail: { code: state.authCode, message: 'Сессия недействительна' } }, 401)
    if (path === '/auth/me') return reply({ ...makeUser(1), is_admin: state.admin })
    if (path === '/chats') return reply([{ id: 77, title: 'Мой чат', created_at: date }])
    if (path.startsWith('/chats/')) return reply([])
    if (path.startsWith('/admin/')) {
      state.adminRequests++
      if (!state.admin) return reply({ detail: 'Доступ разрешён только администратору' }, 403)
      if (state.failLoad) return reply({ detail: 'Сервис временно недоступен' }, 503)
    }
    if (path === '/admin/summary') return reply({ users: state.users.length,
      active_users: state.users.filter((item) => item.is_active).length,
      blocked_users: state.users.filter((item) => !item.is_active).length, admins: 1,
      chats: 4, messages: 10, checks: 6, checks_by_status: { PROPERTY_HOLDS: 3, PROPERTY_VIOLATED: 2, TIMEOUT: 1 } })
    if (path === '/admin/users') {
      const q = (url.searchParams.get('q') || '').toLowerCase()
      const filter = url.searchParams.get('state') || 'all'
      const limit = Number(url.searchParams.get('limit') || 25)
      const offset = Number(url.searchParams.get('offset') || 0)
      const users = state.users.filter((item) => item.email.toLowerCase().includes(q) && (filter === 'all' || item.is_active === (filter === 'active'))).sort((a, b) => b.id - a.id)
      return reply({ items: users.slice(offset, offset + limit), total: users.length, limit, offset })
    }
    if (path.startsWith('/admin/users/') && request.method() === 'PATCH') {
      const user = state.users.find((item) => item.id === Number(path.split('/').at(-1)))
      state.patches++
      user.is_active = request.postDataJSON().is_active
      state.audit.unshift({ id: state.audit.length + 1, actor_id: 1, actor_email: 'admin@example.com',
        target_id: user.id, target_email: user.email, action: user.is_active ? 'unblock_user' : 'block_user', created_at: date })
      return reply(user)
    }
    if (path.startsWith('/admin/users/') && path.endsWith('/access') && request.method() === 'PUT') {
      const user = state.users.find((item) => item.id === Number(path.split('/').at(-2)))
      const body = request.postDataJSON()
      state.accessBodies = [...(state.accessBodies || []), body]
      // как на сервере: доступ до конца выбранного дня по Москве = 21:00 UTC этого дня
      user.access_until = body.access_until_date ? `${body.access_until_date}T21:00:00Z` : null
      user.daily_limit = body.daily_limit
      user.requests_today = 0
      return reply(user)
    }
    if (path === '/admin/audit') return reply({ items: state.audit, total: state.audit.length, limit: 20, offset: 0 })
    return reply({ detail: 'Not found' }, 404)
  })
  await page.goto(`/#/${route}`)
  return state
}

const userSection = (page) => page.getByRole('region', { name: 'Пользователи', exact: true })

async function search(page, email) {
  await page.getByLabel('Поиск по email').fill(email)
  await page.getByRole('button', { name: 'Найти', exact: true }).click()
  await expect(page.getByText('Загружаем данные панели…')).toHaveCount(0)
}

test('admin route restores despite a selected chat and exposes metrics and paged users', async ({ page }) => {
  await setup(page)
  await expect(page.getByRole('heading', { name: 'Админ-панель', exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Статистика приложения' })).toContainText('Пользователи')
  await expect(userSection(page).getByRole('row')).toHaveCount(26)
  await page.getByRole('button', { name: 'Страницы пользователей: далее', exact: true }).click()
  await expect(userSection(page).getByRole('row')).toHaveCount(4)
  await expect(userSection(page).getByText('admin@example.com', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Админ-панель', exact: true })).toBeVisible()
})

test('the account bar opens the admin panel and returns to chats', async ({ page }) => {
  await setup(page, { route: 'chat' })
  await page.getByRole('button', { name: 'Админ-панель', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Админ-панель', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'К моим чатам', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Мой чат', exact: true })).toBeVisible()
})

test('blocking requires confirmation and updates status, metrics, filters and audit', async ({ page }) => {
  const state = await setup(page)
  await search(page, 'user2@example.com')
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'Заблокировать user2@example.com', exact: true }).click()
  expect(state.patches).toBe(0)
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Заблокировать user2@example.com', exact: true }).click()
  await expect(userSection(page).getByText('Заблокирован', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Журнал действий' })).toContainText('Блокировка')
  expect(state.patches).toBe(1)
  await page.getByLabel('Статус аккаунта').selectOption('blocked')
  await expect(userSection(page).getByText('user2@example.com', { exact: true })).toBeVisible()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Разблокировать user2@example.com', exact: true }).click()
  await expect(userSection(page).getByText('Пользователи не найдены. Измените поиск или фильтр.')).toBeVisible()
  expect(state.audit.map((item) => item.action)).toEqual(['unblock_user', 'block_user'])
})

test('admin accounts are protected and empty search is explained', async ({ page }) => {
  await setup(page)
  await search(page, 'admin@example.com')
  await expect(userSection(page).getByText('Защищённый аккаунт', { exact: true })).toBeVisible()
  await expect(userSection(page).getByRole('button', { name: /Заблокировать/ })).toHaveCount(0)
  await search(page, 'missing-user')
  await expect(userSection(page).getByText('Пользователи не найдены. Измените поиск или фильтр.')).toBeVisible()
})

test('ordinary users never request or see admin data even at the direct URL', async ({ page }) => {
  const state = await setup(page, { admin: false })
  await expect(page.getByRole('heading', { name: 'Доступ запрещён', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Админ-панель', exact: true })).toHaveCount(0)
  expect(state.adminRequests).toBe(0)
  await expect(page.locator('.admin-table')).toHaveCount(0)
})

test('a revoked role clears previously displayed admin data on 403', async ({ page }) => {
  const state = await setup(page)
  await expect(userSection(page).getByRole('row')).toHaveCount(26)
  state.admin = false
  await page.getByRole('button', { name: 'Обновить данные', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Доступ запрещён', exact: true })).toBeVisible()
  await expect(page.locator('.admin-table')).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('pimo.token'))).toBe('test-admin-token')
})

test('failed loading can be retried without logging out', async ({ page }) => {
  const state = await setup(page, { failLoad: true })
  await expect(page.getByRole('alert')).toContainText('Сервис временно недоступен')
  state.failLoad = false
  await page.getByRole('button', { name: 'Повторить', exact: true }).click()
  await expect(userSection(page).getByRole('row')).toHaveCount(26)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('expired admin session clears the panel and requests login', async ({ page }) => {
  const state = await setup(page)
  await expect(userSection(page).getByRole('row')).toHaveCount(26)
  state.expired = true
  await page.getByRole('button', { name: 'Обновить данные', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Войти в PIMO', exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('Сессия истекла')
  await expect(page.locator('.admin-table')).toHaveCount(0)
})

test('blocked account gets an explicit message and the panel fits mobile', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const state = await setup(page)
  await expect(userSection(page).getByRole('row')).toHaveCount(26)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('mobile-admin.png'), fullPage: true })
  state.expired = true; state.authCode = 'account_blocked'
  await page.getByRole('button', { name: 'Обновить данные', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Аккаунт заблокирован')
})

test('admin grants agent access with an end date and a daily limit, then closes it', async ({ page }) => {
  const state = await setup(page)
  await search(page, 'user5@')
  const row = userSection(page).getByRole('row', { name: /user5@example.com/ })
  await expect(row).toContainText('Не выдан')
  await row.getByRole('button', { name: 'Изменить доступ user5@example.com' }).click()
  await row.getByLabel('Доступ до (включительно, МСК)').fill('2026-12-10')
  await row.getByLabel('Запросов в сутки').fill('20')
  await row.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'user5@example.com: доступ до 10.12.2026, 20 запросов в сутки.' })).toBeVisible()
  expect(state.accessBodies).toEqual([{ access_until_date: '2026-12-10', daily_limit: 20 }])
  await expect(row).toContainText('10.12.2026')
  await expect(row).toContainText('Лимит 20/сутки · сегодня 0')

  // пустой лимит = без лимита; затем закрыть доступ
  await row.getByRole('button', { name: 'Изменить доступ user5@example.com' }).click()
  await row.getByLabel('Запросов в сутки').fill('')
  await row.getByRole('button', { name: 'Сохранить' }).click()
  await expect(row).toContainText('Без лимита')
  await row.getByRole('button', { name: 'Изменить доступ user5@example.com' }).click()
  await row.getByRole('button', { name: 'Закрыть доступ' }).click()
  await expect(row).toContainText('Не выдан')
  expect(state.accessBodies.slice(1)).toEqual([{ access_until_date: '2026-12-10', daily_limit: null }, { access_until_date: null, daily_limit: null }])
})

test('administrators are shown without access limits and cannot be edited', async ({ page }) => {
  await setup(page)
  await search(page, 'admin@')
  const row = userSection(page).getByRole('row', { name: /admin@example.com/ })
  await expect(row).toContainText('Без ограничений')
  await expect(row.getByRole('button', { name: /Изменить доступ/ })).toHaveCount(0)
})
