export class GeometryRuntimeError extends Error {
  constructor(message, sourceStepId = null) {
    super(message)
    this.name = 'GeometryRuntimeError'
    this.sourceStepId = sourceStepId
  }
}

function assertCurrent(isCurrent) {
  if (!isCurrent()) throw new GeometryRuntimeError('Stale GeoGebra execution was cancelled')
}

function waitForGeoGebraUpdate() {
  if (typeof globalThis.requestAnimationFrame !== 'function') return Promise.resolve()
  return new Promise(resolve => {
    globalThis.requestAnimationFrame(() => globalThis.requestAnimationFrame(resolve))
  })
}

export function verifyArtifactLabels(api, artifact, { isCurrent = () => true } = {}) {
  for (const step of artifact.steps ?? []) {
    assertCurrent(isCurrent)
    for (const label of step.expected_labels ?? []) {
      const displayedValue = api.getValueString?.(label, false)
      const hasUndefinedValue = displayedValue != null && /(?:^|=\s*)\?$/.test(String(displayedValue).trim())
      if (!api.exists(label) || !api.isDefined(label) || hasUndefinedValue) {
        throw new GeometryRuntimeError(`GeoGebra object ${label} is missing or undefined`, step.source_step_id)
      }
    }
  }
}

export async function executeArtifact(api, artifact, { isCurrent = () => true } = {}) {
  for (const step of artifact.steps ?? []) {
    for (const command of step.commands ?? []) {
      assertCurrent(isCurrent)
      if (api.evalCommand(command) !== true) {
        throw new GeometryRuntimeError(`GeoGebra rejected a command for step ${step.source_step_id}`, step.source_step_id)
      }
    }
    await waitForGeoGebraUpdate()
    verifyArtifactLabels(api, { steps: [step] }, { isCurrent })
  }
}
