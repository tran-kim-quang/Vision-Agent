import { expect, test } from '@playwright/test'


const artifact = (id, title) => ({
  id,
  version: 1,
  app: '3d',
  title,
  givens: [{ id: 'given-a', text: 'Điểm A < B', source_text: '<script>unsafe()</script>' }],
  goals: [{ id: 'goal-1', text: 'Quan sát hình' }],
  display_choices: [{ id: 'choice-1', text: 'Chọn hệ trục vuông góc' }],
  steps: [{ source_step_id: 'A', commands: ['A=(0,0,0)'], expected_labels: ['A'] }],
})

function frames(sessionId, requestId, figure, { done = true } = {}) {
  const values = [
    { type: 'request_start', session_id: sessionId, request_id: requestId },
    { type: 'geometry_artifact', session_id: sessionId, request_id: requestId, artifact: figure },
  ]
  if (done) values.push({ type: 'done', supervisor_responded: false })
  return values.map(value => `data: ${JSON.stringify(value)}\n\n`).join('')
}

async function installStreamMock(page, responses) {
  await page.addInitScript(payloads => {
    const originalFetch = window.fetch.bind(window)
    let call = 0
    window.fetch = (input, init = {}) => {
      if (!String(input).endsWith('/api/stream')) return originalFetch(input, init)
      const response = payloads[call++] ?? { chunks: [] }
      const encoder = new TextEncoder()
      return Promise.resolve(new Response(new ReadableStream({
        async start(controller) {
          for (const chunk of response.chunks) {
            if (chunk.delay) await new Promise(resolve => setTimeout(resolve, chunk.delay))
            if (init.signal?.aborted) {
              controller.error(new DOMException('Aborted', 'AbortError'))
              return
            }
            controller.enqueue(encoder.encode(chunk.text))
          }
          controller.close()
        },
      }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } }))
    }
  }, responses)
}

async function installGeoGebraMock(page) {
  await page.route('https://www.geogebra.org/apps/deployggb.js', route => route.fulfill({
    contentType: 'application/javascript',
    body: `window.__ggbMetrics = window.__ggbMetrics || { instances: 0, removed: 0, restored: [] };
    window.GGBApplet = function (params) {
      window.__ggbMetrics.instances += 1;
      const labels = new Set();
      let xml = '<geogebra></geogebra>';
      const api = {
        evalCommand(command) { const match = command.match(/^([A-Za-z][A-Za-z0-9_]*)\\s*=/); if (match) labels.add(match[1]); xml = '<constructed></constructed>'; return true; },
        exists(label) { return labels.has(label); },
        isDefined(label) { return labels.has(label); },
        getXML() { return xml; },
        setXML(value) { xml = value; labels.add('A'); window.__ggbMetrics.restored.push(value); },
        remove() { window.__ggbMetrics.removed += 1; },
      };
      window.__latestGgbApi = api;
      this.inject = function () { setTimeout(() => params.appletOnLoad(api), 0); };
      this.remove = function () {};
    };`,
  }))
}

async function send(page, text) {
  await page.locator('.input-field').fill(text)
  await page.locator('.send-btn').click()
}

test('split SSE keeps the artifact on disconnect and renders unsafe text literally', async ({ page }) => {
  const session = 'session-one'
  const body = frames(session, 'request-one', artifact('artifact-one', '<img onerror=alert(1)> Hình'), { done: false }).trimEnd()
  await page.addInitScript(value => localStorage.setItem('va_session_id', value), session)
  await installStreamMock(page, [{ chunks: [
    { text: body.slice(0, 19) },
    { text: body.slice(19, 73) },
    { text: body.slice(73) },
  ] }])
  await installGeoGebraMock(page)
  await page.goto('/')

  await send(page, 'Vẽ hình')
  const card = page.getByTestId('geometry-artifact')
  await expect(card).toContainText('<img onerror=alert(1)> Hình')
  await expect(card.locator('img')).toHaveCount(0)
  await expect(card).toContainText('<script>unsafe()</script>')
  await expect(page.locator('.geometry-stream-error')).toContainText('kết thúc trước khi hoàn tất')
  await card.getByRole('button', { name: 'Mở hình' }).click()
  await expect(page.getByRole('region', { name: /GeoGebra/ })).toBeVisible()
  await expect(page.getByText('Hình đã hiển thị')).toBeVisible()
})

test('two turns keep separate artifacts and opening the latest selects its workspace', async ({ page }) => {
  const session = 'session-two'
  await page.addInitScript(value => localStorage.setItem('va_session_id', value), session)
  await installStreamMock(page, [
    { chunks: [{ text: frames(session, 'request-a', artifact('artifact-a', 'Hình thứ nhất')) }] },
    { chunks: [{ text: frames(session, 'request-b', artifact('artifact-b', 'Hình thứ hai')) }] },
  ])
  await installGeoGebraMock(page)
  await page.goto('/')

  await send(page, 'Yêu cầu một')
  await expect(page.getByTestId('geometry-artifact')).toHaveCount(1)
  await send(page, 'Yêu cầu hai')
  await expect(page.getByTestId('geometry-artifact')).toHaveCount(2)
  await page.getByTestId('geometry-artifact').nth(1).getByRole('button', { name: 'Mở hình' }).click()
  await expect(page.getByRole('region', { name: /Hình thứ hai/ })).toBeVisible()
})

test('closing and reopening restores the user-edited GeoGebra state', async ({ page }) => {
  const session = 'session-restore'
  await page.addInitScript(value => localStorage.setItem('va_session_id', value), session)
  await installStreamMock(page, [{ chunks: [{ text: frames(session, 'request-edit', artifact('artifact-edit', 'Hình chỉnh sửa')) }] }])
  await installGeoGebraMock(page)
  await page.goto('/')

  await send(page, 'Hình cần chỉnh sửa')
  await page.getByRole('button', { name: 'Mở hình' }).click()
  await expect(page.getByText('Hình đã hiển thị')).toBeVisible()
  await page.evaluate(() => {
    window.__latestGgbApi.setXML('<geogebra edited="true"></geogebra>')
    window.__ggbMetrics.restored = []
  })
  await page.getByRole('button', { name: 'Đóng' }).click()
  await page.getByRole('button', { name: 'Mở hình' }).click()
  await expect(page.getByText('Hình đã hiển thị')).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.__ggbMetrics.restored.at(-1))).toBe('<geogebra edited="true"></geogebra>')
})

test('new chat aborts a delayed stream and removes its viewer', async ({ page }) => {
  const session = 'session-three'
  const body = frames(session, 'request-old', artifact('artifact-old', 'Hình cũ'))
  const split = body.indexOf('\n\n') + 2
  await page.addInitScript(value => localStorage.setItem('va_session_id', value), session)
  await installStreamMock(page, [{ chunks: [
    { text: body.slice(0, split) },
    { text: body.slice(split), delay: 300 },
  ] }])
  await page.goto('/')

  await send(page, 'Yêu cầu cũ')
  await page.getByRole('button', { name: /New chat/ }).click()
  await page.waitForTimeout(450)
  await expect(page.getByTestId('geometry-artifact')).toHaveCount(0)
  await expect(page.locator('.geogebra-viewer')).toHaveCount(0)
})
