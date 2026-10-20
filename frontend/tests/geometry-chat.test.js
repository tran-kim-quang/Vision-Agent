import assert from 'node:assert/strict'
import test from 'node:test'

import { consumeSSEBuffer, createGeometryTurn, reduceGeometryTurn } from '../src/geometry/chatState.js'


const artifact = { id: 'artifact-1', title: '<img onerror=alert(1)> Hình', givens: [{ text: 'A < B', source_text: '<script>x</script>' }], goals: [], display_choices: [], steps: [] }


test('artifact and final text stay in one assistant turn', () => {
  let turn = createGeometryTurn('session')
  turn = reduceGeometryTurn(turn, { type: 'request_start', session_id: 'session', request_id: 'request' })
  turn = reduceGeometryTurn(turn, { type: 'geometry_artifact', session_id: 'session', request_id: 'request', artifact })
  turn = reduceGeometryTurn(turn, { type: 'token', agent: 'supervisor', content: 'Lời giải' })
  turn = reduceGeometryTurn(turn, { type: 'done' })
  assert.equal(turn.text, 'Lời giải')
  assert.equal(turn.artifacts.length, 1)
  assert.equal(turn.finalized, true)
})

test('artifact survives error and explicit finalization without text', () => {
  let turn = reduceGeometryTurn(createGeometryTurn('session'), { type: 'request_start', session_id: 'session', request_id: 'request' })
  turn = reduceGeometryTurn(turn, { type: 'geometry_artifact', session_id: 'session', request_id: 'request', artifact })
  turn = reduceGeometryTurn(turn, { type: 'error', content: 'disconnected' })
  turn = reduceGeometryTurn(turn, { type: 'finalize' })
  assert.equal(turn.artifacts[0].title, '<img onerror=alert(1)> Hình')
  assert.equal(turn.streamError, 'disconnected')
  assert.equal(turn.finalized, true)
})

test('duplicate artifacts and late or foreign events are ignored', () => {
  let turn = reduceGeometryTurn(createGeometryTurn('session'), { type: 'request_start', session_id: 'session', request_id: 'request' })
  turn = reduceGeometryTurn(turn, { type: 'geometry_artifact', session_id: 'other', request_id: 'request', artifact })
  assert.equal(turn.artifacts.length, 0)
  turn = reduceGeometryTurn(turn, { type: 'geometry_artifact', session_id: 'session', request_id: 'request', artifact })
  turn = reduceGeometryTurn(turn, { type: 'geometry_artifact', session_id: 'session', request_id: 'request', artifact })
  turn = reduceGeometryTurn(turn, { type: 'done' })
  const frozen = reduceGeometryTurn(turn, { type: 'geometry_artifact', session_id: 'session', request_id: 'request', artifact: { ...artifact, id: 'late' } })
  assert.equal(frozen.artifacts.length, 1)
})

test('split SSE frames and final unterminated event are retained', () => {
  let state = consumeSSEBuffer('', 'data: {"type":"request_')
  assert.deepEqual(state.events, [])
  state = consumeSSEBuffer(state.buffer, 'start"}\n\ndata: {"type":"done"}', true)
  assert.deepEqual(state.events.map(event => event.type), ['request_start', 'done'])
  assert.equal(state.buffer, '')
})
