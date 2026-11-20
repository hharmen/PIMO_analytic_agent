import { test, expect } from '@playwright/test'

const date = '2026-10-31T10:00:00Z'
const user = { id: 1, email: 'test@example.com', created_at: date }
const makeMessage = (id, role, content) => ({ id, role, content, created_at: new Date(Date.parse(date) + id * 1000).toISOString() })
const makeRun = (id, status = 'PROPERTY_VIOLATED') => ({
  id, status, created_at: new Date(Date.parse(date) + (id * 2 - 0.5) * 1000).toISOString(),
  model_json: { variables: [], properties: status === 'MODEL_INVALID' ? {} : [{ id: 'P1', description: 'Отменённая заявка не исполняется' }] },
  result_json: {
    engine: 'TLC', status, results: [{
      property_id: 'P1', property_type: 'forbidden_state', status,
      message: 'Результат проверки P1', related_requirements: ['Запрет исполнения после отмены'],
      counterexample: status === 'PROPERTY_VIOLATED' ? { steps: [
        { number: 0, state: { status: 'Created' } },
        { number: 1, transition: 'Execute', state: { status: 'Executed', cancelled: true } },
      ] } : null,
    }],
  },
})

async function mockCore(page, { authenticated = true, sendStatus, noCheck = false, failSend = false, expired = false, answerText } = {}) {
  const state = { chats: [], messages: [], checks: [], sends: 0, registered: false }
  await page.addInitScript((authenticated) => {
    if (authenticated) sessionStorage.setItem('pimo.token', 'test-token')
  }, authenticated)
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api', '')
    const method = request.method()
    const reply = (data, status = 200) => route.fulfill({ status, json: data })
    if (path === '/auth/register') { state.registered = true; return reply(user, 201) }
    if (path === '/auth/login') return reply({ access_token: 'test-token', token_type: 'bearer' })
    if (request.headers().authorization !== 'Bearer test-token') return reply({ detail: 'Нет токена' }, 401)
    if (expired) return reply({ detail: 'Сессия истекла' }, 401)
    if (path === '/auth/me') return reply(user)
    if (path === '/chats' && method === 'GET') return reply(state.chats)
    if (path === '/chats' && method === 'POST') {
      const chat = { id: state.chats.length + 1, title: 'Новый чат', created_at: date }
      state.chats.unshift(chat)
      return reply(chat, 201)
    }
    const id = Number(path.split('/')[2])
    if (method === 'DELETE') {
      state.chats = state.chats.filter((chat) => chat.id !== id)
      return route.fulfill({ status: 204 })
    }
    if (path.endsWith('/checks')) return reply(state.checks)
    if (path.endsWith('/messages') && method === 'GET') return reply(state.messages)
    if (path.endsWith('/messages') && method === 'POST') {
      state.sends++
      const content = request.postDataJSON().content
      const sent = makeMessage(state.messages.length + 1, 'user', content)
      state.messages.push(sent)
      state.chats.find((chat) => chat.id === id).title = content.slice(0, 60)
      if (failSend) return reply({ detail: 'Агент не смог ответить. Сообщение сохранено' }, 500)
      const skipCheck = noCheck || state.noCheck
      const answer = makeMessage(state.messages.length + 1, 'assistant', answerText ?? (skipCheck ? 'Уточните условия отмены.' : 'Исполнение возможно после отмены.'))
      state.messages.push(answer)
      const run = skipCheck ? null : makeRun(state.sends, state.sendStatus || sendStatus)
      if (run) state.checks.push(run)
      return reply({ user_message: sent, assistant_message: answer, check_run: run }, 201)
    }
    return reply({ detail: 'Unknown endpoint' }, 404)
  })
  return state
}

async function submitRequirements(page, text = 'Проверь отмену заявки', open = true) {
  await page.getByLabel('Требования к системе').fill(text)
  await page.getByRole('button', { name: 'Проверить требования', exact: true }).click()
  if (open) await openAnswer(page)
  else await expect(page.locator('.message-preview-assistant')).toHaveCount(1)
}

async function openAnswer(page, index = 0) {
  await page.getByRole('button', { name: /^Открыть ответ агента:/ }).nth(index).click()
  await expect(page.getByRole('heading', { name: 'Ответ агента', exact: true })).toBeVisible()
}

test('registration, login, token and real response contract', async ({ page }) => {
  const state = await mockCore(page, { authenticated: false })
  await page.goto('/#/input')
  await page.getByRole('button', { name: 'Создать аккаунт', exact: true }).click()
  await page.getByLabel('Email', { exact: true }).fill(user.email)
  await page.getByLabel('Пароль', { exact: true }).fill('password123')
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click()
  await submitRequirements(page)
  await expect(page.getByRole('heading', { name: 'Найдено нарушение' })).toBeVisible()
  await expect(page.getByText('Контрпример: путь к нарушению')).toBeVisible()
  await expect(page.getByText('Запрет исполнения после отмены', { exact: true })).toBeVisible()
  expect(state.registered).toBe(true)
  expect(state.sends).toBe(1)
  await page.getByRole('button', { name: 'К переписке', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Проверь отмену заявки' })).toBeVisible()
})

test('continuation preserves the timeline and opens the correct check after reload', async ({ page }) => {
  const state = await mockCore(page)
  await page.goto('/#/input')
  await submitRequirements(page, 'Проверь отмену заявки', false)
  await page.getByLabel('Продолжить диалог', { exact: true }).fill('При отмене approved сбрасывается.')
  await expect(page.locator('.message-preview')).toHaveCount(2)
  state.sendStatus = 'PROPERTY_HOLDS'
  await page.getByRole('button', { name: 'Отправить агенту' }).click()
  await expect(page.locator('.message-preview')).toHaveCount(4)
  expect(state.chats).toHaveLength(1)
  await openAnswer(page, 0)
  await expect(page.locator('.check-run')).toHaveCount(1)
  await expect(page.getByRole('heading', { name: 'Найдено нарушение' })).toBeVisible()
  await page.getByRole('button', { name: 'К переписке', exact: true }).click()
  await openAnswer(page, 1)
  await expect(page.getByRole('heading', { name: 'Свойства выполнены' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Найдено нарушение' })).toHaveCount(0)
  await page.reload()
  await expect(page.locator('.check-run')).toHaveCount(1)
  await expect(page.getByRole('heading', { name: 'Свойства выполнены' })).toBeVisible()
  await page.getByRole('button', { name: 'К переписке', exact: true }).click()
  await page.reload()
  await expect(page.locator('.message-preview')).toHaveCount(4)
  await page.getByRole('button', { name: 'Все проверки', exact: true }).click()
  await expect(page.locator('.check-run')).toHaveCount(2)
  await page.getByRole('button', { name: 'К переписке', exact: true }).click()
  await page.getByRole('button', { name: 'Удалить чат', exact: true }).click()
  await page.getByRole('button', { name: 'Да, удалить' }).click()
  await expect(page.getByLabel('Требования к системе')).toBeVisible()
  expect(state.chats).toHaveLength(0)
})

test('clarification without check result is displayed without a verdict', async ({ page }) => {
  await mockCore(page, { noCheck: true })
  await page.goto('/#/input')
  await submitRequirements(page)
  await expect(page.getByText('Уточните условия отмены.', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Проверки этого ответа · 0' })).toBeVisible()
  await expect(page.locator('.check-run')).toHaveCount(0)
})

for (const status of ['TIMEOUT', 'STATE_LIMIT_REACHED', 'MODEL_INVALID', 'ENGINE_ERROR']) {
  test(`${status} is never shown as successful verification`, async ({ page }) => {
    await mockCore(page, { sendStatus: status })
    await page.goto('/#/input')
    await submitRequirements(page)
    await expect(page.getByText('Успешная проверка всех свойств не подтверждена. Изучите детали результата.')).toBeVisible()
    await expect(page.getByText('Свойства выполнены', { exact: true })).toHaveCount(0)
  })
}

test('agent error reconciles saved message and preserves draft', async ({ page }) => {
  const state = await mockCore(page, { failSend: true })
  await page.goto('/#/input')
  await page.getByLabel('Требования к системе').fill('Исходные требования')
  await page.getByRole('button', { name: 'Проверить требования', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Сообщение сохранено')
  await expect(page.locator('.message-preview')).toHaveCount(1)
  expect(state.sends).toBe(1)
  await expect(page.getByLabel('Продолжить диалог', { exact: true })).toHaveValue('Исходные требования')
})

test('expired session clears token and requests login', async ({ page }) => {
  await mockCore(page, { expired: true })
  await page.goto('/#/input')
  await expect(page.getByRole('heading', { name: 'Войти в PIMO' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('Сессия истекла')
  expect(await page.evaluate(() => sessionStorage.getItem('pimo.token'))).toBeNull()
})

test('TXT content reaches API; unsupported and oversized files do not', async ({ page }) => {
  const state = await mockCore(page)
  await page.goto('/#/input')
  const fileInput = page.locator('input[type=file]')
  await fileInput.setInputFiles({ name: 'requirements.pdf', mimeType: 'application/pdf', buffer: Buffer.from('PDF') })
  await expect(page.getByRole('alert')).toContainText('Поддерживается TXT')
  await fileInput.setInputFiles({ name: 'long.txt', mimeType: 'text/plain', buffer: Buffer.from('x'.repeat(20001)) })
  await expect(page.getByRole('alert')).toContainText('больше 20000')
  const content = 'Заявку нельзя исполнить после отмены.'
  await fileInput.setInputFiles({ name: 'requirements.txt', mimeType: 'text/plain', buffer: Buffer.from(content) })
  await expect(page.getByLabel('Требования к системе')).toHaveValue(content)
  await page.getByRole('button', { name: 'Проверить требования', exact: true }).click()
  await expect(page.locator('.message-preview')).toHaveCount(2)
  expect(state.messages[0].content).toBe(content)
})

test('successful verification shows the scope of the model', async ({ page }) => {
  await mockCore(page, { sendStatus: 'PROPERTY_HOLDS' })
  await page.goto('/#/input')
  await submitRequirements(page)
  await expect(page.getByRole('heading', { name: 'Свойства выполнены' })).toBeVisible()
  await expect(page.getByText('Свойства выполнены в исследованной конечной модели при заданных ограничениях. Это не доказывает корректность реальной системы.')).toBeVisible()
  await expect(page.getByText('Контрпример: путь к нарушению')).toHaveCount(0)
})

test('mobile requirements and result remain usable without horizontal overflow', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockCore(page)
  await page.goto('/#/input')
  await submitRequirements(page)
  await expect(page.getByRole('heading', { name: 'Найдено нарушение' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('mobile-result.png'), fullPage: true })
})


test('agent Markdown renders headings, tables and code safely with an opaque header', async ({ page }, testInfo) => {
  await mockCore(page, { answerText: [
    '## Результат: нарушение найдено',
    '',
    '**Причина:** признак `approved` не сброшен.',
    '',
    '| Шаг | Действие | Состояние |',
    '| --- | --- | --- |',
    '| 0 | Заявка создана | Created |',
    '| 1 | Исполнение | **Executed** |',
    '',
    '> Уточните условия отмены.',
    '',
    '```json',
    '{"approved": true}',
    '```',
    '',
    '<script>window.markdownExecuted = true</script>',
    '[Опасная ссылка](javascript:alert(1))',
  ].join('\n') })
  await page.goto('/#/input')
  await submitRequirements(page)
  const answer = page.locator('.message-assistant')
  await expect(answer.getByRole('heading', { name: 'Результат: нарушение найдено' })).toBeVisible()
  await expect(answer.getByRole('table')).toBeVisible()
  await expect(answer.getByRole('cell', { name: 'Executed', exact: true })).toBeVisible()
  await expect(answer.locator('strong').filter({ hasText: 'Причина:' })).toBeVisible()
  await expect(answer.locator('pre code')).toHaveText('{"approved": true}')
  await expect(answer.locator('script')).toHaveCount(0)
  await expect(answer.locator('a')).not.toHaveAttribute('href', /^javascript:/)
  expect(await page.evaluate(() => window.markdownExecuted)).toBeUndefined()
  await expect(page.locator('.topbar')).toHaveCSS('background-color', 'rgb(243, 238, 230)')
  await page.screenshot({ path: testInfo.outputPath('formatted-report.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('saved chats are searchable and switching restores each independent history', async ({ page }) => {
  await mockCore(page)
  const chats = [{ id: 2, title: 'Оплата заказа', created_at: date }, { id: 1, title: 'Отмена заявки', created_at: date }]
  const histories = {
    1: [makeMessage(1, 'user', 'Правила отмены'), makeMessage(2, 'assistant', 'Ответ об отмене')],
    2: [makeMessage(3, 'user', 'Правила оплаты'), makeMessage(4, 'assistant', 'Ответ об оплате')],
  }
  await page.route('**/api/chats**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const path = new URL(route.request().url()).pathname
    const id = Number(path.split('/')[3])
    await route.fulfill({ json: path === '/api/chats' ? chats : path.endsWith('/checks') ? [] : histories[id] })
  })
  await page.goto('/#/input')
  const sidebar = page.getByRole('complementary', { name: 'Ваши чаты' })
  await expect(sidebar.getByRole('button', { name: /Оплата заказа/ })).toBeVisible()
  await sidebar.getByRole('button', { name: /Отмена заявки/ }).click()
  await expect(page.getByText('Ответ об отмене', { exact: true })).toBeVisible()
  await page.getByLabel('Продолжить диалог', { exact: true }).fill('Черновик про отмену')
  await sidebar.getByRole('button', { name: /Оплата заказа/ }).click()
  await expect(page.getByText('Ответ об оплате', { exact: true })).toBeVisible()
  await expect(page.getByText('Ответ об отмене', { exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Продолжить диалог', { exact: true })).toHaveValue('')
  await sidebar.getByRole('button', { name: /Отмена заявки/ }).click()
  await expect(page.getByLabel('Продолжить диалог', { exact: true })).toHaveValue('Черновик про отмену')
  await sidebar.getByRole('button', { name: /Оплата заказа/ }).click()
  await page.reload()
  await expect(page.getByText('Ответ об оплате', { exact: true })).toBeVisible()
  await page.getByLabel('Поиск чатов').fill('отмена')
  await expect(sidebar.getByRole('button', { name: /Оплата заказа/ })).toHaveCount(0)
  await expect(sidebar.getByRole('button', { name: /Отмена заявки/ })).toBeVisible()
  await page.getByLabel('Поиск чатов').fill('нет такого чата')
  await expect(sidebar.getByText('Чаты не найдены.')).toBeVisible()
  await page.getByLabel('Поиск чатов').fill('')
  await page.getByRole('button', { name: 'Новый чат', exact: true }).click()
  await expect(page.getByLabel('Требования к системе')).toBeVisible()
  await expect(sidebar.getByRole('button', { name: /Отмена заявки/ })).toBeVisible()
})

test('clarification after a check never reuses the previous verdict', async ({ page }) => {
  const state = await mockCore(page)
  await page.goto('/#/input')
  await submitRequirements(page, 'Исходные требования', false)
  state.noCheck = true
  await page.getByLabel('Продолжить диалог', { exact: true }).fill('Какие условия нужны?')
  await page.getByRole('button', { name: 'Отправить агенту' }).click()
  await expect(page.locator('.message-preview-assistant')).toHaveCount(2)
  await openAnswer(page, 1)
  await expect(page.getByRole('heading', { name: 'Проверки этого ответа · 0' })).toBeVisible()
  await expect(page.locator('.check-run')).toHaveCount(0)
  await expect(page.getByText('Уточните условия отмены.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'К переписке', exact: true }).click()
  await openAnswer(page, 0)
  await expect(page.locator('.check-run')).toHaveCount(1)
})

test('history remains visible during a reply and Ctrl+Enter submits once', async ({ page }) => {
  const state = await mockCore(page)
  await page.goto('/#/input')
  await submitRequirements(page, 'Исходные требования', false)
  let release
  const pending = new Promise((resolve) => { release = resolve })
  await page.route('**/api/chats/*/messages', async (route) => {
    if (route.request().method() === 'POST') await pending
    await route.fallback()
  })
  const composer = page.getByLabel('Продолжить диалог', { exact: true })
  await composer.fill('Уточнение условий')
  await composer.press('Control+Enter')
  await expect(page.getByRole('status')).toContainText('Агент анализирует')
  await expect(page.locator('.message-preview-assistant')).toHaveCount(1)
  await expect(composer).toBeDisabled()
  release()
  await expect(page.locator('.message-preview-assistant')).toHaveCount(2)
  await expect(composer).toHaveValue('')
  expect(state.sends).toBe(2)
})

test('long replies stay compact and chat layout works on mobile', async ({ page }, testInfo) => {
  const fullAnswer = '## Подробный ответ\n\n' + 'Длинное объяснение требований и найденных проблем. '.repeat(200)
  await mockCore(page, { answerText: fullAnswer })
  await page.goto('/#/input')
  await submitRequirements(page, 'Проверка длинного ответа', false)
  await expect(page.locator('.message-preview')).toHaveCount(2)
  expect(await page.locator('.message-preview-assistant').evaluate((element) => element.getBoundingClientRect().height)).toBeLessThan(300)
  await page.screenshot({ path: testInfo.outputPath('desktop-messenger.png'), fullPage: true })
  await openAnswer(page)
  await expect(page.locator('.message-assistant')).toContainText('Длинное объяснение требований и найденных проблем. '.repeat(200).trim())
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'К переписке', exact: true }).click()
  await expect(page.getByLabel('Продолжить диалог', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('mobile-messenger.png'), fullPage: true })
})
