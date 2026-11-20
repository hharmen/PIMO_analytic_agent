import { test, expect } from '@playwright/test'

const now = new Date('2026-11-20T16:00:00Z')
const tokenFor = (id, lifetime = 3600) => [
  Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url'),
  Buffer.from(JSON.stringify({ sub: String(id), iat: now.getTime() / 1000, exp: now.getTime() / 1000 + lifetime })).toString('base64url'),
  'mock-signature', // Server auth is mocked here; backend tests verify real signatures.
].join('.')
const history = [
  { id: 1, role: 'user', content: 'Исходные требования', created_at: now.toISOString() },
  { id: 2, role: 'assistant', content: 'Сохранённый ответ агента', created_at: now.toISOString() },
]

async function setup(page, { initiallyRejected = false, initialLifetime = 3600 } = {}) {
  await page.clock.install({ time: now })
  const state = { rejected: initiallyRejected, code: 'token_expired', accountId: 1, wrongPassword: false, networkDown: false, messageGets: 0, meFailures: 0, sends: 0, waitForSend: null, sendFinished: false }
  await page.addInitScript((token) => {
    if (sessionStorage.getItem('test.auth-initialized')) return
    sessionStorage.setItem('test.auth-initialized', 'true')
    sessionStorage.setItem('pimo.token', token)
    sessionStorage.setItem('pimo.chat', '1')
  }, tokenFor(1, initialLifetime))
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api', '')
    const reply = (json, status = 200) => route.fulfill({ status, json })
    if (path === '/auth/login') {
      if (state.wrongPassword) return reply({ detail: 'Неверный email или пароль' }, 401)
      state.rejected = false
      return reply({ access_token: tokenFor(state.accountId, 14400), token_type: 'bearer' })
    }
    if (state.networkDown && path === '/auth/me') {
      await route.abort('failed')
      state.meFailures++
      return
    }
    if (state.rejected) return reply({ detail: { code: state.code, message: state.code === 'token_expired' ? 'Сессия истекла. Войдите снова.' : 'Сессия недействительна. Войдите снова.' } }, 401)
    if (path === '/auth/me') return reply({ id: state.accountId, email: state.accountId === 1 ? 'owner@example.com' : 'other@example.com', created_at: now.toISOString() })
    if (path === '/chats') return reply(state.accountId === 1 ? [{ id: 1, title: 'Сохранённый чат', created_at: now.toISOString() }] : [])
    if (path.endsWith('/checks')) return reply([])
    if (path.endsWith('/messages') && request.method() === 'GET') { state.messageGets++; return reply(history) }
    if (path.endsWith('/messages') && request.method() === 'POST') {
      state.sends++
      if (state.waitForSend) await state.waitForSend
      const response = {
        user_message: { id: 3, role: 'user', content: 'Старый запрос', created_at: now.toISOString() },
        assistant_message: { id: 4, role: 'assistant', content: 'Поздний ответ старой сессии', created_at: now.toISOString() },
        check_run: null,
      }
      await reply(response, 201).catch(() => {}) // The expiry timer can cancel the browser request.
      state.sendFinished = true
      return
    }
    return reply({ detail: 'Not found' }, 404)
  })
  await page.goto('/#/chat')
  return state
}

async function login(page) {
  await page.getByLabel('Email', { exact: true }).fill('owner@example.com')
  await page.getByLabel('Пароль', { exact: true }).fill('password123')
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
}

async function expectLogin(page, message) {
  await expect(page.getByRole('heading', { name: 'Войти в PIMO', exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText(message)
  await expect(page.locator('.message-preview')).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('pimo.token'))).toBeNull()
  expect(await page.evaluate(() => sessionStorage.getItem('pimo.chat'))).toBeNull()
}

test('expiry on an idle page removes private data and restores the draft in the same chat after login', async ({ page }) => {
  const state = await setup(page)
  const composer = page.getByLabel('Продолжить диалог', { exact: true })
  await composer.fill('Неотправленное уточнение')
  await page.clock.fastForward(3600 * 1000)
  await expectLogin(page, 'Сессия истекла')
  // Recovery survives a reload, but credentials and chat data stay hidden.
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Войти в PIMO', exact: true })).toBeVisible()
  await login(page)
  await expect(page.getByRole('heading', { name: 'Сохранённый чат', exact: true })).toBeVisible()
  await expect(composer).toHaveValue('Неотправленное уточнение')
  await expect(page.locator('.message-preview')).toHaveCount(2)
  expect(state.sends).toBe(0)
})

test('another account never receives the previous account draft or conversation', async ({ page }) => {
  const state = await setup(page)
  await page.getByLabel('Продолжить диалог', { exact: true }).fill('Приватный черновик первого аккаунта')
  await page.clock.fastForward(3600 * 1000)
  await expectLogin(page, 'Сессия истекла')
  state.accountId = 2
  await login(page)
  await expect(page.getByText('other@example.com', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Требования к системе')).toHaveValue('')
  await expect(page.getByText('Сохранённый чат', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('pimo.session-recovery'))).toBeNull()
})

test('a server 401 during send requests login without retrying or reconciling with an invalid token', async ({ page }) => {
  const state = await setup(page)
  await page.getByLabel('Продолжить диалог', { exact: true }).fill('Новый текст')
  state.rejected = true
  await page.getByRole('button', { name: 'Отправить агенту', exact: true }).click()
  await expectLogin(page, 'Сессия истекла')
  expect(state.messageGets).toBe(1)
  await login(page)
  await expect(page.getByLabel('Продолжить диалог', { exact: true })).toHaveValue('Новый текст')
  await expect(page.locator('.message-preview')).toHaveCount(2)
})

test('a deleted or invalid user is detected when returning to the tab', async ({ page }) => {
  const state = await setup(page)
  await expect(page.locator('.message-preview')).toHaveCount(2)
  state.rejected = true
  state.code = 'invalid_token'
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expectLogin(page, 'Сессия недействительна')
})

test('invalid credentials remain a login error and a correct retry works', async ({ page }) => {
  const state = await setup(page, { initiallyRejected: true })
  await expectLogin(page, 'Сессия истекла')
  state.wrongPassword = true
  await login(page)
  await expect(page.getByRole('alert')).toHaveText('Неверный email или пароль')
  expect(await page.evaluate(() => sessionStorage.getItem('pimo.token'))).toBeNull()
  state.wrongPassword = false
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Сохранённый чат', exact: true })).toBeVisible()
})

test('a network failure does not log out an otherwise valid session', async ({ page }) => {
  const state = await setup(page)
  await expect(page.locator('.message-preview')).toHaveCount(2)
  state.networkDown = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect.poll(() => state.meFailures).toBe(1)
  await expect(page.getByLabel('Продолжить диалог', { exact: true })).toBeEnabled()
  expect(await page.evaluate(() => sessionStorage.getItem('pimo.token'))).toBe(tokenFor(1))
})

test('expiry during a pending LLM request cannot repopulate the UI after another account logs in', async ({ page }) => {
  const state = await setup(page)
  let release
  state.waitForSend = new Promise((resolve) => { release = resolve })
  await page.getByLabel('Продолжить диалог', { exact: true }).fill('Старый запрос')
  await page.getByRole('button', { name: 'Отправить агенту', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Агент анализирует')
  await expect.poll(() => state.sends).toBe(1)
  await page.clock.fastForward(3600 * 1000)
  await expectLogin(page, 'Сессия истекла')
  state.accountId = 2
  await login(page)
  await expect(page.getByText('other@example.com', { exact: true })).toBeVisible()
  release()
  await expect.poll(() => state.sendFinished).toBe(true)
  await expect(page.getByLabel('Требования к системе')).toHaveValue('')
  await expect(page.getByText('Поздний ответ старой сессии', { exact: false })).toHaveCount(0)
})

test('an already expired token is handled without briefly displaying saved messages', async ({ page }) => {
  await setup(page, { initiallyRejected: true, initialLifetime: -1 })
  await expectLogin(page, 'Сессия истекла')
  await expect(page.getByRole('button', { name: /^Открыть ответ агента:/ })).toHaveCount(0)
})
