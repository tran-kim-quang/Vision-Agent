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

export function verifyArtifactLabels(api, artifact, { isCurrent = () => true } = {}) {
  for (const step of artifact.steps ?? []) {
    assertCurrent(isCurrent)
    for (const label of step.expected_labels ?? []) {
      if (!api.exists(label) || !api.isDefined(label)) {
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
    verifyArtifactLabels(api, { steps: [step] }, { isCurrent })
  }
}
