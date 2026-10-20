import assert from 'node:assert/strict'
import test from 'node:test'

import { loadGeoGebra } from '../src/geometry/loader.js'
import { GeometryRuntimeError, executeArtifact } from '../src/geometry/runtime.js'


function fakeDocument(behavior = 'load') {
  const scripts = []
  const win = {}
  return {
    scripts,
    defaultView: win,
    createElement() { return { dataset: {} } },
    head: {
      appendChild(script) {
        scripts.push(script)
        queueMicrotask(() => {
          if (behavior === 'load') {
            win.GGBApplet = function GGBApplet() {}
            script.onload()
          } else if (behavior === 'error') script.onerror(new Error('blocked'))
        })
      },
    },
  }
}


test('loader shares one in-flight script load', async () => {
  const document = fakeDocument()
  const [a, b] = await Promise.all([loadGeoGebra({ document }), loadGeoGebra({ document })])
  assert.equal(a, b)
  assert.equal(document.scripts.length, 1)
  assert.equal(document.scripts[0].src, 'https://www.geogebra.org/apps/deployggb.js')
})

test('failed script load is cleared so the same document can retry', async () => {
  const document = fakeDocument('error')
  await assert.rejects(loadGeoGebra({ document, timeoutMs: 50 }), /load/i)
  document.head.appendChild = script => {
    document.scripts.push(script)
    document.defaultView.GGBApplet = function GGBApplet() {}
    queueMicrotask(() => script.onload())
  }
  await loadGeoGebra({ document, timeoutMs: 50 })
  assert.equal(document.scripts.length, 2)
})

test('executeArtifact stops on command failure and names the source step', async () => {
  const calls = []
  const api = { evalCommand(command) { calls.push(command); return command !== 'bad' }, exists: () => true, isDefined: () => true }
  const artifact = { steps: [{ source_step_id: 'A', commands: ['ok', 'bad', 'never'], expected_labels: ['A'] }] }
  await assert.rejects(executeArtifact(api, artifact, { isCurrent: () => true }), error => error instanceof GeometryRuntimeError && error.sourceStepId === 'A')
  assert.deepEqual(calls, ['ok', 'bad'])
})

test('executeArtifact checks expected labels', async () => {
  const api = { evalCommand: () => true, exists: label => label !== 'missing', isDefined: () => true }
  const artifact = { steps: [{ source_step_id: 'M', commands: ['M=1'], expected_labels: ['M', 'missing'] }] }
  await assert.rejects(executeArtifact(api, artifact, { isCurrent: () => true }), /missing/)
})

test('stale execution performs no command', async () => {
  let calls = 0
  const api = { evalCommand() { calls += 1; return true }, exists: () => true, isDefined: () => true }
  const artifact = { steps: [{ source_step_id: 'A', commands: ['A=(0,0,0)'], expected_labels: ['A'] }] }
  await assert.rejects(executeArtifact(api, artifact, { isCurrent: () => false }), /stale/i)
  assert.equal(calls, 0)
})
