import { expect, test } from '@playwright/test'
import artifacts from './fixtures/compiled-artifacts.json' with { type: 'json' }


test.describe.configure({ mode: 'serial', timeout: 90000 })

async function installArtifactStream(page, artifact, sessionId) {
  await page.addInitScript(({ figure, session }) => {
    localStorage.setItem('va_session_id', session)
    const requestId = `real-${figure.id}`
    const events = [
      { type: 'request_start', session_id: session, request_id: requestId },
      { type: 'geometry_artifact', session_id: session, request_id: requestId, artifact: figure },
      { type: 'done', supervisor_responded: false },
    ]
    const body = events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')
    const originalFetch = window.fetch.bind(window)
    window.fetch = (input, init) => String(input).endsWith('/api/stream')
      ? Promise.resolve(new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }))
      : originalFetch(input, init)
  }, { figure: artifact, session: sessionId })
}

async function openArtifact(page, artifact) {
  await installArtifactStream(page, artifact, `session-${artifact.id}`)
  await page.goto('/')
  await page.locator('.input-field').fill('Mở hình kiểm thử')
  await page.locator('.send-btn').click()
  await page.getByRole('button', { name: 'Mở hình' }).click()
  await expect(page.getByText('Hình đã hiển thị')).toBeVisible({ timeout: 60000 })
  const containerId = await page.locator('.geogebra-canvas').getAttribute('id')
  return containerId
}

async function coordinates(page, appletId, label) {
  return page.evaluate(({ id, object }) => {
    const api = document.getElementById(id)?.__geogebraApi
    if (!api) throw new Error(`GeoGebra API ${id} is not available`)
    return [api.getXcoord(object), api.getYcoord(object), api.getZcoord(object)]
  }, { id: appletId, object: label })
}

function expectCoordinates(actual, expected) {
  for (let index = 0; index < expected.length; index += 1) {
    expect(Math.abs(actual[index] - expected[index])).toBeLessThan(1e-8)
  }
}

test('@real midpoint, projection and line-plane intersection use the real GeoGebra API', async ({ page }, testInfo) => {
  const started = performance.now()
  let appletId = await openArtifact(page, artifacts.tetrahedron)
  const coldMs = performance.now() - started
  expectCoordinates(await coordinates(page, appletId, 'M'), [2, 0, 0])
  const interaction = await page.evaluate(async id => {
    const api = document.getElementById(id).__geogebraApi
    const updateStarted = performance.now()
    api.setCoords('A', 2, 0, 0)
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    const parameterUpdateMs = performance.now() - updateStarted
    const stamps = []
    await new Promise(resolve => {
      const sample = timestamp => {
        stamps.push(timestamp)
        if (stamps.length === 31) resolve()
        else requestAnimationFrame(sample)
      }
      requestAnimationFrame(sample)
    })
    const intervals = stamps.slice(1).map((stamp, index) => stamp - stamps[index])
    return {
      parameterUpdateMs,
      averageFrameMs: intervals.reduce((sum, value) => sum + value, 0) / intervals.length,
      maxFrameMs: Math.max(...intervals),
      midpoint: [api.getXcoord('M'), api.getYcoord('M'), api.getZcoord('M')],
    }
  }, appletId)
  expectCoordinates(interaction.midpoint, [3, 0, 0])

  const warmStarted = performance.now()
  await page.getByRole('button', { name: 'Đóng' }).click()
  await page.getByRole('button', { name: 'Mở hình' }).click()
  await expect(page.getByText('Hình đã hiển thị')).toBeVisible({ timeout: 60000 })
  const warmMs = performance.now() - warmStarted

  await page.getByRole('button', { name: 'Đóng' }).click()
  await page.reload()
  appletId = await openArtifact(page, artifacts.projection)
  expectCoordinates(await coordinates(page, appletId, 'H'), [1, 2, 0])

  await page.getByRole('button', { name: 'Đóng' }).click()
  await page.reload()
  appletId = await openArtifact(page, artifacts['line-plane'])
  expectCoordinates(await coordinates(page, appletId, 'I'), [1, 2, 0])

  const metrics = `cold=${coldMs.toFixed(0)}ms warm=${warmMs.toFixed(0)}ms parameter-update=${interaction.parameterUpdateMs.toFixed(1)}ms frame-average=${interaction.averageFrameMs.toFixed(1)}ms frame-max=${interaction.maxFrameMs.toFixed(1)}ms`
  console.log(`[geogebra-performance] ${metrics}`)
  testInfo.annotations.push({ type: 'performance', description: metrics })
})

test('@real undefined parallel intersection reports a runtime failure', async ({ page }) => {
  await installArtifactStream(page, artifacts['undefined-intersection'], 'session-parallel')
  await page.goto('/')
  await page.locator('.input-field').fill('Mở hình song song')
  await page.locator('.send-btn').click()
  await page.getByRole('button', { name: 'Mở hình' }).click()
  await expect(page.getByRole('alert')).toContainText(/missing or undefined|rejected/i, { timeout: 60000 })
  await expect(page.getByText('Hình đã hiển thị')).toHaveCount(0)
})

for (const [name, label] of [['function2d', 'f'], ['surface', 's']]) {
  test(`@real ${name} creates a visible graphic`, async ({ page }, testInfo) => {
    const appletId = await openArtifact(page, artifacts[name])
    const visible = await page.evaluate(({ id, object }) => {
      const api = document.getElementById(id)?.__geogebraApi
      return api.exists(object) && api.isDefined(object) && api.getVisible(object)
    }, { id: appletId, object: label })
    expect(visible).toBe(true)

    const canvas = page.locator('.geogebra-canvas')
    await canvas.hover()
    await page.mouse.wheel(0, -400)
    if (name === 'surface') {
      const box = await canvas.boundingBox()
      if (box) {
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
        await page.mouse.down()
        await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 30)
        await page.mouse.up()
      }
    }
    await testInfo.attach(`${name}.png`, { body: await page.screenshot(), contentType: 'image/png' })
  })
}
