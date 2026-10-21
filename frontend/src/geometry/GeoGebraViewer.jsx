import { useEffect, useId, useRef, useState } from 'react'

import { loadGeoGebra } from './loader'
import { applyArtifactDisplay, executeArtifact, verifyArtifactLabels } from './runtime'


const READY_TIMEOUT_MS = 20000

export default function GeoGebraViewer({ artifact, stateCache, onClose }) {
  const reactId = useId().replace(/[^A-Za-z0-9_-]/g, '')
  const containerId = `geogebra-${reactId}`
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState(null)
  const [retryKey, setRetryKey] = useState(0)
  const epochRef = useRef(0)

  useEffect(() => {
    const epoch = ++epochRef.current
    let active = true
    let api = null
    let applet = null
    let readyTimer = null
    let resizeObserver = null
    const isCurrent = () => active && epochRef.current === epoch

    setStatus('loading')
    setError(null)
    loadGeoGebra().then(GGBApplet => {
      if (!isCurrent()) return
      readyTimer = setTimeout(() => {
        if (isCurrent()) {
          setStatus('error')
          setError(new Error('GeoGebra initialization timed out'))
        }
      }, READY_TIMEOUT_MS)
      // The artifact's graphing mode denotes 2D. GeoGebra's Graphing Calculator
      // disables geometric commands (e.g. Midpoint); Geometry supports these
      // and function plots together. Keep Graphing for function-only figures.
      const planarConstruction = artifact.app === 'graphing'
        && artifact.spec?.steps.some(step => step.op !== 'function2d')
      const container = document.getElementById(containerId)
      const resize = () => {
        if (!isCurrent() || !container) return
        const { clientWidth: width, clientHeight: height } = container
        if (width > 0 && height > 0) api?.setSize?.(width, height)
      }
      applet = new GGBApplet({
        id: containerId,
        appName: planarConstruction ? 'geometry' : artifact.app,
        showAxes: true,
        width: container?.clientWidth || 900,
        height: container?.clientHeight || 620,
        // ResizeObserver sets real dimensions; avoid deployggb scaling them again.
        disableAutoScale: true,
        showToolBar: true,
        showAlgebraInput: true,
        showMenuBar: false,
        enableRightClick: false,
        useBrowserForJS: false,
        appletOnLoad: async loadedApi => {
          if (!isCurrent()) {
            loadedApi.remove?.()
            return
          }
          clearTimeout(readyTimer)
          api = loadedApi
          if (container) container.__geogebraApi = loadedApi
          resize()
          if (container && typeof ResizeObserver === 'function') {
            resizeObserver = new ResizeObserver(resize)
            resizeObserver.observe(container)
          }
          setStatus('executing')
          try {
            const snapshot = stateCache.get(artifact.id)
            if (snapshot) {
              api.setXML(snapshot)
              try {
                verifyArtifactLabels(api, artifact, { isCurrent })
              } catch {
                stateCache.delete(artifact.id)
                api.setXML('<geogebra format="5.0"></geogebra>')
                await executeArtifact(api, artifact, { isCurrent })
                applyArtifactDisplay(api, artifact)
              }
            } else {
              await executeArtifact(api, artifact, { isCurrent })
              applyArtifactDisplay(api, artifact)
            }
            if (isCurrent()) setStatus('ready')
          } catch (cause) {
            if (isCurrent()) {
              setStatus('error')
              setError(cause)
            }
          }
        },
      }, true)
      applet.inject(containerId)
    }).catch(cause => {
      if (isCurrent()) {
        setStatus('error')
        setError(cause)
      }
    })

    return () => {
      active = false
      clearTimeout(readyTimer)
      resizeObserver?.disconnect()
      if (api) {
        try {
          const xml = api.getXML?.()
          if (xml) stateCache.set(artifact.id, String(xml))
        } catch { /* an incomplete applet has no state worth retaining */ }
        api.remove?.()
        const container = document.getElementById(containerId)
        if (container) delete container.__geogebraApi
      } else {
        applet?.remove?.()
      }
    }
  }, [artifact, containerId, retryKey, stateCache])

  const retry = () => setRetryKey(value => value + 1)

  return (
    <section className="geogebra-viewer" aria-label={`Hình GeoGebra: ${artifact.title}`}>
      <div className="geogebra-toolbar">
        <div className="geogebra-heading">
          <strong className="geogebra-title" title={artifact.title}>{artifact.title}</strong>
          <span>{status === 'ready' ? 'Hình đã hiển thị' : status === 'executing' ? 'Đang dựng hình…' : status === 'error' ? 'Không thể dựng hình' : 'Đang tải GeoGebra…'}</span>
        </div>
        <button type="button" onClick={onClose}>Đóng</button>
      </div>
      {status === 'error' && (
        <div className="geogebra-error" role="alert">
          <p>{error?.message ?? 'GeoGebra không phản hồi.'}</p>
          <button type="button" onClick={retry}>Thử lại</button>
          <details>
            <summary>Xem các bước dựng</summary>
            <ol>{artifact.steps.map(step => <li key={step.source_step_id}>{step.source_step_id}: {step.commands.join('; ')}</li>)}</ol>
          </details>
        </div>
      )}
      <div id={containerId} className="geogebra-canvas" hidden={status === 'error'} />
    </section>
  )
}
