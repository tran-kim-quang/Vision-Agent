export function createGeometryTurn(sessionId) {
  return {
    id: globalThis.crypto?.randomUUID?.() ?? `turn-${Date.now()}-${Math.random()}`,
    role: 'assistant',
    sessionId,
    requestId: null,
    text: '',
    artifacts: [],
    streamError: null,
    finalized: false,
  }
}

export function reduceGeometryTurn(turn, event) {
  if (!event || turn.finalized) return turn

  if (event.type === 'request_start') {
    if (event.session_id !== turn.sessionId || turn.requestId) return turn
    return { ...turn, requestId: event.request_id }
  }

  if (event.type === 'geometry_artifact') {
    if (!turn.requestId || event.session_id !== turn.sessionId || event.request_id !== turn.requestId) return turn
    if (!event.artifact?.id || turn.artifacts.some(item => item.id === event.artifact.id)) return turn
    return { ...turn, artifacts: [...turn.artifacts, event.artifact] }
  }

  if (event.type === 'token' && event.agent === 'supervisor') {
    return { ...turn, text: turn.text + (event.content ?? '') }
  }

  if (event.type === 'error') {
    return { ...turn, streamError: event.content || 'Kết nối bị gián đoạn.' }
  }

  if (event.type === 'done' || event.type === 'finalize') {
    return {
      ...turn,
      text: event.text ?? turn.text,
      streamError: event.error ?? turn.streamError,
      finalized: true,
    }
  }

  return turn
}

export function consumeSSEBuffer(buffer, chunk, flush = false) {
  const lines = `${buffer}${chunk}`.split(/\r?\n/)
  const remainder = flush ? '' : (lines.pop() ?? '')
  const events = []

  for (const line of lines) {
    if (!line.startsWith('data:')) continue
    const payload = line.slice(5).trimStart()
    if (!payload) continue
    try {
      events.push(JSON.parse(payload))
    } catch {
      // Ignore malformed activity frames while keeping the stream alive.
    }
  }

  return { buffer: remainder, events }
}
