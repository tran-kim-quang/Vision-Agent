const SCRIPT_URL = 'https://www.geogebra.org/apps/deployggb.js'
const loads = new WeakMap()

export function loadGeoGebra({ document: doc = globalThis.document, timeoutMs = 20000 } = {}) {
  if (!doc) return Promise.reject(new Error('GeoGebra requires a document'))
  const win = doc.defaultView ?? globalThis
  if (typeof win.GGBApplet === 'function') return Promise.resolve(win.GGBApplet)
  if (loads.has(doc)) return loads.get(doc)

  const promise = new Promise((resolve, reject) => {
    const script = doc.createElement('script')
    const timer = setTimeout(() => reject(new Error('GeoGebra script load timed out')), timeoutMs)
    const finish = callback => value => {
      clearTimeout(timer)
      callback(value)
    }
    script.src = SCRIPT_URL
    script.async = true
    script.dataset.geogebraLoader = 'true'
    script.onload = finish(() => {
      if (typeof win.GGBApplet !== 'function') reject(new Error('GeoGebra script loaded without GGBApplet'))
      else resolve(win.GGBApplet)
    })
    script.onerror = finish(() => reject(new Error('GeoGebra script failed to load')))
    doc.head.appendChild(script)
  })
  loads.set(doc, promise)
  promise.catch(() => loads.delete(doc))
  return promise
}
