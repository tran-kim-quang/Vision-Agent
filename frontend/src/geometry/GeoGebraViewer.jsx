import { useEffect, useId, useRef, useState } from 'react'

import { loadGeoGebra } from './loader'
import { executeArtifact, verifyArtifactLabels } from './runtime'


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
      applet = new GGBApplet({
        id: containerId,
        appName: artifact.app,
        width: 900,
        height: 620,
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
          const container = document.getElementById(containerId)
          if (container) container.__geogebraApi = loadedApi
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
              }
            } else {
              await executeArtifact(api, artifact, { isCurrent })
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
        <span>{status === 'ready' ? 'Hình đã hiển thị' : status === 'executing' ? 'Đang dựng hình…' : status === 'error' ? 'Không thể dựng hình' : 'Đang tải GeoGebra…'}</span>
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
