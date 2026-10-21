import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import artifacts from './fixtures/compiled-artifacts.json' with { type: 'json' }


test.describe.configure({ mode: 'serial', timeout: 90000 })

async function installArtifactStream(page, artifact, sessionId) {
  await page.addInitScript(({ figures, session }) => {
    localStorage.setItem('va_session_id', session)
    let turn = 0
    const originalFetch = window.fetch.bind(window)
    window.fetch = (input, init) => {
      if (!String(input).endsWith('/api/stream')) return originalFetch(input, init)
      const figure = figures[turn++]
      const requestId = `real-${turn}-${figure.id}`
      const events = [
        { type: 'request_start', session_id: session, request_id: requestId },
        { type: 'geometry_artifact', session_id: session, request_id: requestId, artifact: figure },
        { type: 'done', supervisor_responded: false },
      ]
      const body = events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')
      return Promise.resolve(new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }))
    }
  }, { figures: Array.isArray(artifact) ? artifact : [artifact], session: sessionId })
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

test('@real documented command fills the exact region requested by the user', async ({ page }) => {
  const figure = process.env.GEOGEBRA_REGION_ARTIFACT
    ? JSON.parse(readFileSync(process.env.GEOGEBRA_REGION_ARTIFACT, 'utf8'))
    : artifacts['integral-region']
  const region = figure.spec.steps.find(step => step.op === 'command' && step.name === 'IntegralBetween')
  expect(region).toBeTruthy()
  const id = await openArtifact(page, figure)
  const values = await page.evaluate(({ id, label }) => {
    const api = document.getElementById(id).__geogebraApi
    return { defined: api.isDefined(label), visible: api.getVisible(label), filling: api.getFilling(label),
      value: api.getValue(label), xml: api.getXML() }
  }, { id, label: region.id })
  expect(values.defined).toBe(true)
  expect(values.visible).toBe(true)
  expect(values.filling).toBeCloseTo(region.fill_opacity, 8)
  expect(values.filling).toBeGreaterThan(0)
  expect(values.value).toBeCloseTo(4.5, 8)
  expect(values.xml).toContain('name="IntegralBetween"')
  await page.screenshot({ path: '/tmp/geogebra-region-in-app.png' })
})

test('@real the same documented-command path constructs a cone', async ({ page }) => {
  const id = await openArtifact(page, artifacts['documented-cone'])
  const value = await page.evaluate(id => {
    const api = document.getElementById(id).__geogebraApi
    return { visible: api.getVisible('solid'), volume: api.getValue('Volume(solid)'), filling: api.getFilling('solid') }
  }, id)
  expect(value.visible).toBe(true)
  expect(value.volume).toBeCloseTo(16 * Math.PI / 3, 8)
  expect(value.filling).toBeCloseTo(0.3, 8)
})

test('@real drawing labels show short captions instead of equations', async ({ page }) => {
  const figure = structuredClone(artifacts.sphere)
  const captions = { O: 'Tâm O', ball: 'Mặt cầu (S)', tangent: 'Tiếp tuyến d' }
  for (const step of figure.spec.steps) if (captions[step.id]) step.caption = captions[step.id]
  const id = await openArtifact(page, figure)
  const labels = await page.evaluate(id => {
    const api = document.getElementById(id).__geogebraApi
    const xml = new DOMParser().parseFromString(api.getXML(), 'application/xml')
    return Object.fromEntries(['O', 'ball', 'tangent'].map(label => {
      const object = Array.from(xml.querySelectorAll('element')).find(el => el.getAttribute('label') === label)
      return [label, { mode: object.querySelector('labelMode')?.getAttribute('val'),
        caption: object.querySelector('caption')?.getAttribute('val'), defined: api.isDefined(label) }]
    }))
  }, id)
  for (const [label, caption] of Object.entries(captions)) {
    expect(labels[label]).toEqual({ mode: '3', caption, defined: true })
  }
  await page.screenshot({ path: '/tmp/geogebra-short-captions.png' })
})

for (const source of ['fixture', 'live']) {
  test(`@real ${source === 'live' ? '@live ' : ''}${source} sphere creates a surface and a tangent line`, async ({ page }) => {
    test.skip(source === 'live' && !process.env.GEOGEBRA_SPHERE_ARTIFACT, 'requires the exported live sphere artifact')
    const figure = source === 'fixture' ? artifacts.sphere : JSON.parse(readFileSync(process.env.GEOGEBRA_SPHERE_ARTIFACT, 'utf8'))
    const spec = figure.spec
    const sphere = spec.steps.find(step => step.op === 'sphere')
    const lines = spec.steps.filter(step => step.op === 'line')
    const points = Object.fromEntries(spec.steps.filter(step => step.op === 'point').map(step => [step.id, step.coords]))
    const radius = sphere.radius ?? Math.hypot(...points[sphere.through].map((coord, index) => coord - points[sphere.center][index]))
    const id = await openArtifact(page, figure)
    const values = await page.evaluate(({ id, sphere, lines }) => {
      const api = document.getElementById(id).__geogebraApi
      return {
        type: api.getObjectType(sphere.id), visible: api.getVisible(sphere.id), defined: api.isDefined(sphere.id),
        volume: api.getValue(`Volume(${sphere.id})`),
        centerToLines: lines.map(line => api.getValue(`Distance(${sphere.center},${line.id})`)),
      }
    }, { id, sphere, lines })
    expect(values.type).toBe('sphere')
    expect(values.visible).toBe(true)
    expect(values.defined).toBe(true)
    expect(values.volume).toBeCloseTo(4 * Math.PI * radius ** 3 / 3, 8)
    expect(values.centerToLines.some(distance => Math.abs(distance - radius) < 1e-8)).toBe(true)
    await page.screenshot({ path: `/tmp/geogebra-sphere-${source}.png` })
  })
}

test('@real constructed lines are distinct from axes and the applet fills its workspace', async ({ page }) => {
  await page.setViewportSize({ width: 1850, height: 900 })
  const id = await openArtifact(page, artifacts.vertical2d)
  const before = await page.evaluate(id => {
    const el = document.getElementById(id)
    const api = el.__geogebraApi
    return { type: api.getObjectType('d'), equation: api.getValueString('d'), color: api.getColor('d'),
      graphics: api.getGraphicsOptions(1), container: el.getBoundingClientRect().toJSON(),
      frame: el.querySelector('.GeoGebraFrame')?.getBoundingClientRect().toJSON() }
  }, id)
  await page.screenshot({ path: '/tmp/geogebra-display-fixed.png' })
  expect(before.type).toBe('line')
  expect(before.color.toUpperCase()).toBe('#2563EB')
  expect(before.graphics.axes.x.visible).toBe(true)
  expect(before.graphics.axes.y.visible).toBe(true)
  expect(before.graphics.grid).toBe(true)
  await expect.poll(() => page.evaluate(id => {
    const el = document.getElementById(id)
    const frame = el.querySelector('.GeoGebraFrame')
    return Math.abs(frame.getBoundingClientRect().width - el.clientWidth)
  }, id)).toBeLessThan(3)
  await page.setViewportSize({ width: 700, height: 820 })
  await expect.poll(() => page.evaluate(id => {
    const el = document.getElementById(id)
    const frame = el.querySelector('.GeoGebraFrame').getBoundingClientRect()
    return Math.max(Math.abs(frame.width - el.clientWidth), Math.abs(frame.height - el.clientHeight))
  }, id)).toBeLessThan(3)
  await page.screenshot({ path: '/tmp/geogebra-display-fixed-small.png' })
})

test('@real one chat switches 2D to 3D to 2D and restores its earlier construction', async ({ page }) => {
  await installArtifactStream(page, [artifacts.vertical2d, artifacts.tetrahedron, artifacts.function2d], 'mixed-dimensions')
  await page.goto('/')
  for (const [index, title] of ['Đường thẳng đứng', 'Tứ diện', 'Đồ thị hàm số'].entries()) {
    await page.locator('.input-field').fill(title)
    await page.locator('.send-btn').click()
    const cards = page.getByTestId('geometry-artifact')
    await expect(cards).toHaveCount(index + 1)
    await expect(cards.nth(index)).toContainText(index === 1 ? '3D' : '2D')
    await cards.nth(index).getByRole('button', { name: 'Mở hình' }).click()
    await expect(page.getByText('Hình đã hiển thị')).toBeVisible({ timeout: 60000 })
    const id = await page.locator('.geogebra-canvas').getAttribute('id')
    if (index === 0) {
      expectCoordinates(await coordinates(page, id, 'I'), [2, 0])
      expectCoordinates(await coordinates(page, id, 'M'), [2, 0.5])
      expectCoordinates(await coordinates(page, id, 'H'), [2, 0])
      const visible = await page.evaluate(id => {
        const api = document.getElementById(id).__geogebraApi
        return ['d', 's', 'triangle', 'f'].every(label => api.isDefined(label) && api.getVisible(label))
      }, id)
      expect(visible).toBe(true)
      expect(await page.evaluate(id => document.getElementById(id).__geogebraApi.getValue('f(2)'), id)).toBeCloseTo(4, 8)
      await page.evaluate(id => document.getElementById(id).__geogebraApi.setCoords('B', 2, 3), id)
    } else if (index === 1) {
      expectCoordinates(await coordinates(page, id, 'D'), [1, 1, 3])
      expectCoordinates(await coordinates(page, id, 'M'), [2, 0, 0])
    } else {
      const value = await page.evaluate(id => {
        const api = document.getElementById(id).__geogebraApi
        return { defined: api.isDefined('f'), value: api.getValue('f(0)') }
      }, id)
      expect(value.defined).toBe(true)
      expect(value.value).toBeCloseTo(0, 8)
    }
    await page.getByRole('button', { name: 'Đóng' }).click()
  }
  await page.getByTestId('geometry-artifact').first().getByRole('button', { name: 'Mở hình' }).click()
  await expect(page.getByText('Hình đã hiển thị')).toBeVisible({ timeout: 60000 })
  const restored = await page.locator('.geogebra-canvas').getAttribute('id')
  expectCoordinates(await coordinates(page, restored, 'B'), [2, 3])
  expectCoordinates(await coordinates(page, restored, 'M'), [2, 1.5])
  expectCoordinates(await coordinates(page, restored, 'I'), [2, 0])
})

test('@real @live model-produced figures preserve the requested geometry in one chat', async ({ page }) => {
  test.skip(!process.env.GEOGEBRA_LIVE_ARTIFACTS, 'enable after the opt-in Python live-model test exports artifacts')
  const figures = JSON.parse(readFileSync(process.env.GEOGEBRA_LIVE_ARTIFACTS, 'utf8'))
  expect(figures.map(figure => figure.app)).toEqual(['graphing', '3d', 'graphing'])
  await installArtifactStream(page, figures, 'live-mixed-dimensions')
  await page.goto('/')
  for (const [index, figure] of figures.entries()) {
    await page.locator('.input-field').fill(figure.title)
    await page.locator('.send-btn').click()
    await page.getByTestId('geometry-artifact').nth(index).getByRole('button', { name: 'Mở hình' }).click()
    await expect(page.getByText('Hình đã hiển thị')).toBeVisible({ timeout: 60000 })
    const id = await page.locator('.geogebra-canvas').getAttribute('id')
    const spec = figure.spec
    if (index === 1) {
      expectCoordinates(await coordinates(page, id, 'D'), [0, 0, 4])
      const midpoint = spec.steps.find(step => step.op === 'midpoint' && [step.a, step.b].sort().join(',') === 'A,B')
      expect(midpoint).toBeTruthy()
      expectCoordinates(await coordinates(page, id, midpoint.id), [2, 0, 0])
    } else {
      const intersection = spec.steps.find(step => step.op === 'intersection')
      expect(intersection).toBeTruthy()
      expectCoordinates(await coordinates(page, id, intersection.id), [index === 0 ? 2 : -1, 0])
    }
    if (index === 2) {
      const fn = spec.steps.find(step => step.op === 'function2d')
      expect(fn.domain).toEqual([-3, 3])
      for (const [x, expected] of [[-2, 4], [0, 0], [2, 4]]) {
        const value = await page.evaluate(({ id, label, x }) => document.getElementById(id).__geogebraApi.getValue(`${label}(${x})`), { id, label: fn.id, x })
        expect(value).toBeCloseTo(expected, 8)
      }
    }
    await page.getByRole('button', { name: 'Đóng' }).click()
  }
})

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
