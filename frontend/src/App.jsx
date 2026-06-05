import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const AGENT_META = {
  supervisor:     { icon: '🎯', label: 'Supervisor',      color: '#818cf8' },
  research_agent: { icon: '🔬', label: 'Research Agent',  color: '#60a5fa' },
  vision_agent:   { icon: '👁️',  label: 'Vision Agent',   color: '#f59e0b' },
  agent:          { icon: '🧠', label: 'Agent Reasoning', color: '#60a5fa' },
  tools:          { icon: '🔧', label: 'Tool Execution',  color: '#34d399' },
}

function agentMeta(name) {
  return AGENT_META[name] ?? { icon: '🤖', label: name, color: '#94a3b8' }
}

// ── Section renderer ───────────────────────────────────────────────────────
function Section({ section }) {
  if (section.type === 'text') {
    return (
      <div className="sec-text">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{section.content}</ReactMarkdown>
      </div>
    )
  }
  if (section.type === 'tool_call') {
    return (
      <div className="sec-tool-call">
        <span className="tool-badge call">⚡ {section.tool}</span>
        {section.args && <code className="tool-args">{section.args}</code>}
      </div>
    )
  }
  if (section.type === 'tool_result') {
    return (
      <div className="sec-tool-result">
        <span className="tool-badge result">📥 {section.tool} result</span>
        <pre className="tool-content">{section.content}</pre>
      </div>
    )
  }
  return null
}

// ── Agent card ─────────────────────────────────────────────────────────────
function AgentCard({ name, sections, isActive }) {
  const bodyRef = useRef(null)
  const meta = agentMeta(name)

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [sections])

  return (
    <div className={`agent-card ${isActive ? 'active' : 'done'}`} style={{ '--accent': meta.color }}>
      <div className="agent-card-header">
        <span className="agent-icon">{meta.icon}</span>
        <span className="agent-name">{meta.label}</span>
        {isActive ? <span className="status-dot active" /> : <span className="status-done">✓</span>}
      </div>
      <div className="agent-card-body" ref={bodyRef}>
        {sections.map((s, i) => <Section key={i} section={s} />)}
        {isActive && sections.length === 0 && <span className="thinking">thinking…</span>}
      </div>
    </div>
  )
}

// ── Main app ───────────────────────────────────────────────────────────────
export default function App() {
  const [input, setInput] = useState('')
  const [attachedImage, setAttachedImage] = useState(null) // { previewUrl, serverPath, name }
  const [isUploading, setIsUploading] = useState(false)
  const [agentData, setAgentData] = useState({})
  const [agentOrder, setAgentOrder] = useState([])
  const [supervisorText, setSupervisorText] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  const supervisorRef = useRef(null)
  const fileInputRef = useRef(null)
  const agentTextAccumRef = useRef({})

  useEffect(() => {
    if (supervisorRef.current) supervisorRef.current.scrollTop = supervisorRef.current.scrollHeight
  }, [supervisorText])

  // ── Image upload ───────────────────────────────────────────────────────────
  const uploadFile = useCallback(async (file) => {
    if (!file?.type.startsWith('image/')) return
    setIsUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/upload', { method: 'POST', body: form })
      if (!res.ok) throw new Error(`Upload failed (${res.status})`)
      const { path } = await res.json()
      setAttachedImage({
        previewUrl: URL.createObjectURL(file),
        serverPath: path,
        name: file.name || 'image',
      })
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setIsUploading(false)
    }
  }, [])

  const removeImage = useCallback(() => {
    setAttachedImage(prev => {
      if (prev?.previewUrl) URL.revokeObjectURL(prev.previewUrl)
      return null
    })
  }, [])

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (file) uploadFile(file)
    e.target.value = ''
  }

  const handlePaste = useCallback((e) => {
    for (const item of e.clipboardData?.items ?? []) {
      if (item.type.startsWith('image/')) {
        e.preventDefault()
        uploadFile(item.getAsFile())
        break
      }
    }
  }, [uploadFile])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file?.type.startsWith('image/')) uploadFile(file)
  }, [uploadFile])

  // ── Agent sections ─────────────────────────────────────────────────────────
  const pushSection = useCallback((agentName, section) => {
    if (section.type === 'text') {
      agentTextAccumRef.current[agentName] =
        (agentTextAccumRef.current[agentName] ?? '') + section.content
    }
    setAgentData(prev => {
      const agent = prev[agentName] ?? { sections: [], isActive: true }
      const sections = [...agent.sections]
      if (section.type === 'text') {
        const last = sections[sections.length - 1]
        if (last?.type === 'text') {
          sections[sections.length - 1] = { type: 'text', content: last.content + section.content }
          return { ...prev, [agentName]: { ...agent, sections } }
        }
      }
      return { ...prev, [agentName]: { ...agent, sections: [...sections, section] } }
    })
  }, [])

  // ── SSE event handler ──────────────────────────────────────────────────────
  const handleEvent = useCallback((event) => {
    switch (event.type) {
      case 'agent_start':
        setAgentOrder(prev => prev.includes(event.agent) ? prev : [...prev, event.agent])
        setAgentData(prev => ({ ...prev, [event.agent]: prev[event.agent] ?? { sections: [], isActive: true } }))
        break
      case 'token':
        if (event.agent === 'supervisor') setSupervisorText(prev => prev + event.content)
        else pushSection(event.agent, { type: 'text', content: event.content })
        break
      case 'tool_call':
        pushSection(event.agent, { type: 'tool_call', tool: event.tool, args: event.args })
        break
      case 'tool_result':
        pushSection(event.agent, { type: 'tool_result', tool: event.tool, content: event.content })
        break
      case 'handoff':
        break
      case 'error':
        setErrorMsg(event.content)
        break
      case 'done':
        setAgentData(prev => {
          const next = {}
          for (const [k, v] of Object.entries(prev)) next[k] = { ...v, isActive: false }
          return next
        })
        if (!event.supervisor_responded) {
          setSupervisorText(prev => {
            if (prev.trim()) return prev
            const accum = agentTextAccumRef.current
            for (const name of ['agent', 'research_agent', 'vision_agent']) {
              if (accum[name]?.trim()) return accum[name]
            }
            for (const [name, text] of Object.entries(accum)) {
              if (name !== 'tools' && text?.trim()) return text
            }
            return prev
          })
        }
        break
      default:
        break
    }
  }, [pushSection])

  // ── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    const hasContent = input.trim() || attachedImage
    if (!hasContent || isStreaming || isUploading) return

    // Build final message — append image path so agents can find it
    let message = input.trim()
    if (attachedImage) {
      message = message
        ? `${message}\n\nImage: ${attachedImage.serverPath}`
        : `Image: ${attachedImage.serverPath}`
    }

    setAgentData({})
    setAgentOrder([])
    setSupervisorText('')
    setErrorMsg('')
    setIsStreaming(true)
    agentTextAccumRef.current = {}
    removeImage()

    try {
      const response = await fetch('/api/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { handleEvent(JSON.parse(line.slice(6))) } catch { /* skip */ }
          }
        }
      }
    } catch (err) {
      setErrorMsg(err.message)
    }

    setIsStreaming(false)
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
  }

  const subAgents = agentOrder.filter(n => n !== 'supervisor')
  const canSend = (input.trim() || attachedImage) && !isStreaming && !isUploading

  return (
    <div className="layout">

      {/* Header */}
      <header className="topbar">
        <div className="topbar-brand">
          <span className="brand-icon">🤖</span>
          <span className="brand-name">Visual Agent System</span>
        </div>
        {isStreaming && (
          <div className="streaming-indicator">
            <span className="dot-pulse" />
            <span>Streaming</span>
          </div>
        )}
      </header>

      {/* Panels */}
      <div className="panels">
        <section className="panel panel-agents">
          <div className="panel-title">
            <span>Agent Activity</span>
            {subAgents.length > 0 && <span className="badge">{subAgents.length}</span>}
          </div>
          <div className="panel-body">
            {subAgents.length === 0
              ? <p className="empty">Sub-agent activity will stream here…</p>
              : subAgents.map(name => (
                  <AgentCard key={name} name={name}
                    sections={agentData[name]?.sections ?? []}
                    isActive={agentData[name]?.isActive ?? false} />
                ))
            }
          </div>
        </section>

        <section className="panel panel-response">
          <div className="panel-title">
            <span>Supervisor Response</span>
            {agentData['supervisor'] && (
              <span className={`badge ${agentData['supervisor'].isActive ? 'active-badge' : ''}`}>
                {agentData['supervisor'].isActive ? 'typing…' : 'done'}
              </span>
            )}
          </div>
          <div className="panel-body response-body" ref={supervisorRef}>
            {!supervisorText && !isStreaming
              ? <p className="empty">The supervisor's final answer will appear here…</p>
              : (
                <div className="response-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{supervisorText}</ReactMarkdown>
                  {isStreaming && supervisorText && <span className="cursor">▊</span>}
                </div>
              )
            }
          </div>
        </section>
      </div>

      {/* Error banner */}
      {errorMsg && (
        <div className="error-banner">
          ⚠️ {errorMsg}
          <button className="error-close" onClick={() => setErrorMsg('')}>✕</button>
        </div>
      )}

      {/* Input bar */}
      <footer className="inputbar">

        {/* Image preview strip */}
        {attachedImage && (
          <div className="image-preview-strip">
            <img src={attachedImage.previewUrl} alt="preview" className="preview-thumb" />
            <div className="preview-info">
              <span className="preview-name">{attachedImage.name}</span>
              <span className="preview-hint">will be sent with your message</span>
            </div>
            <button className="preview-remove" onClick={removeImage} title="Remove image">✕</button>
          </div>
        )}

        {/* Input row */}
        <div className="input-row">

          {/* Attach button */}
          <button
            className="attach-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={isStreaming || isUploading}
            title="Attach image (or paste / drag-and-drop)"
          >
            {isUploading
              ? <span className="spinner small" />
              : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
              )
            }
          </button>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />

          {/* Textarea */}
          <textarea
            className="input-field"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            onPaste={handlePaste}
            onDrop={handleDrop}
            onDragOver={e => e.preventDefault()}
            placeholder={attachedImage
              ? 'Add a message or just send the image…'
              : 'Ask anything… or paste / drag an image here'
            }
            rows={2}
            disabled={isStreaming}
          />

          {/* Send button */}
          <button className="send-btn" onClick={handleSubmit} disabled={!canSend}>
            {isStreaming
              ? <span className="spinner" />
              : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              )
            }
          </button>
        </div>
      </footer>
    </div>
  )
}
