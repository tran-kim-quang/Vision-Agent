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

export function applyArtifactDisplay(api, artifact) {
  if (artifact.app === 'graphing') {
    api.setAxesVisible?.(true, true)
    api.setGridVisible?.(true)
    api.setAxisLabels?.(1, 'x', 'y', '')
  }
  for (const step of artifact.spec?.steps ?? []) {
    const caption = step.caption?.trim()
    api.setLabelStyle?.(step.id, caption ? 3 : 0)
    if (caption) {
      api.setCaption?.(step.id, caption)
      api.setLabelVisible?.(step.id, true)
    }
    if (step.op === 'sphere') {
      api.setColor?.(step.id, 37, 99, 235)
      api.setFilling?.(step.id, 0.25)
      api.setLabelVisible?.(step.id, true)
    }
    if (['line', 'segment', 'function2d'].includes(step.op)) {
      api.setColor?.(step.id, 37, 99, 235)
      api.setLineThickness?.(step.id, 5)
      api.setLabelVisible?.(step.id, true)
    }
    if (step.fill_opacity != null) {
      api.setColor?.(step.id, 245, 158, 11)
      api.setFilling?.(step.id, step.fill_opacity)
      api.setVisible?.(step.id, true)
      const actual = api.getFilling?.(step.id)
      if ((actual != null && (!Number.isFinite(actual) || Math.abs(actual - step.fill_opacity) > 1e-6))
        || (step.fill_opacity > 0 && api.getVisible?.(step.id) === false)) {
        throw new GeometryRuntimeError(`GeoGebra did not apply the requested fill for ${step.id}`, step.id)
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
