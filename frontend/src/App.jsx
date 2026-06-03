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

// ── Section renderer inside an agent card ──────────────────────────────────
function Section({ section }) {
  if (section.type === 'text') {
    return (
      <div className="sec-text">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {section.content}
        </ReactMarkdown>
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
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight
    }
  }, [sections])

  return (
    <div className={`agent-card ${isActive ? 'active' : 'done'}`} style={{ '--accent': meta.color }}>
      <div className="agent-card-header">
        <span className="agent-icon">{meta.icon}</span>
        <span className="agent-name">{meta.label}</span>
        {isActive
          ? <span className="status-dot active" />
          : <span className="status-done">✓</span>}
      </div>
      <div className="agent-card-body" ref={bodyRef}>
        {sections.map((s, i) => <Section key={i} section={s} />)}
        {isActive && sections.length === 0 && (
          <span className="thinking">thinking…</span>
        )}
      </div>
    </div>
  )
}

// ── Main app ───────────────────────────────────────────────────────────────
export default function App() {
  const [input, setInput] = useState('')
  const [agentData, setAgentData] = useState({})   // { name: { sections, isActive } }
  const [agentOrder, setAgentOrder] = useState([]) // preserves insertion order
  const [supervisorText, setSupervisorText] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  const supervisorRef = useRef(null)
  const inputRef = useRef(null)
  // Accumulate each agent's full text outside React state so the 'done'
  // handler can read it synchronously without stale-closure problems.
  const agentTextAccumRef = useRef({})

  useEffect(() => {
    if (supervisorRef.current) {
      supervisorRef.current.scrollTop = supervisorRef.current.scrollHeight
    }
  }, [supervisorText])

  const pushSection = useCallback((agentName, section) => {
    // Keep a plain-object accumulator for the 'done' fallback
    if (section.type === 'text') {
      agentTextAccumRef.current[agentName] =
        (agentTextAccumRef.current[agentName] ?? '') + section.content
    }

    setAgentData(prev => {
      const agent = prev[agentName] ?? { sections: [], isActive: true }
      const sections = [...agent.sections]

      if (section.type === 'text') {
        const last = sections[sections.length - 1]
        if (last && last.type === 'text') {
          sections[sections.length - 1] = { type: 'text', content: last.content + section.content }
          return { ...prev, [agentName]: { ...agent, sections } }
        }
      }
      return { ...prev, [agentName]: { ...agent, sections: [...sections, section] } }
    })
  }, [])

  const handleEvent = useCallback((event) => {
    switch (event.type) {
      case 'agent_start':
        setAgentOrder(prev => prev.includes(event.agent) ? prev : [...prev, event.agent])
        setAgentData(prev => ({
          ...prev,
          [event.agent]: prev[event.agent] ?? { sections: [], isActive: true },
        }))
        break

      case 'token':
        if (event.agent === 'supervisor') {
          setSupervisorText(prev => prev + event.content)
        } else {
          pushSection(event.agent, { type: 'text', content: event.content })
        }
        break

      case 'tool_call':
        pushSection(event.agent, { type: 'tool_call', tool: event.tool, args: event.args })
        break

      case 'tool_result':
        pushSection(event.agent, { type: 'tool_result', tool: event.tool, content: event.content })
        break

      case 'handoff':
        // internal routing message — ignore in UI
        break

      case 'error':
        setErrorMsg(event.content)
        break

      case 'done':
        setAgentData(prev => {
          const next = {}
          for (const [k, v] of Object.entries(prev)) {
            next[k] = { ...v, isActive: false }
          }
          return next
        })
        // Fallback: if the supervisor never generated its own text,
        // promote the last sub-agent's accumulated response into the
        // supervisor panel (research/vision agents often ARE the answer).
        if (!event.supervisor_responded) {
          setSupervisorText(prev => {
            if (prev.trim()) return prev
            const accum = agentTextAccumRef.current
            // Prefer the inner LLM node ('agent'), then outer agent nodes
            const priority = ['agent', 'research_agent', 'vision_agent']
            for (const name of priority) {
              if (accum[name]?.trim()) return accum[name]
            }
            // Last resort: any non-tools accumulated text
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

  const handleSubmit = async () => {
    if (!input.trim() || isStreaming) return

    // Reset state
    setAgentData({})
    setAgentOrder([])
    setSupervisorText('')
    setErrorMsg('')
    setIsStreaming(true)
    agentTextAccumRef.current = {}

    try {
      const response = await fetch('/api/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input }),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // hold incomplete line

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              handleEvent(JSON.parse(line.slice(6)))
            } catch { /* skip malformed */ }
          }
        }
      }
    } catch (err) {
      setErrorMsg(err.message)
    }

    setIsStreaming(false)
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  // Sub-agents only (exclude supervisor from left panel)
  const subAgents = agentOrder.filter(n => n !== 'supervisor')

  return (
    <div className="layout">

      {/* ── Header ── */}
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

      {/* ── Main panels ── */}
      <div className="panels">

        {/* Left: agent activity */}
        <section className="panel panel-agents">
          <div className="panel-title">
            <span>Agent Activity</span>
            {subAgents.length > 0 && (
              <span className="badge">{subAgents.length}</span>
            )}
          </div>
          <div className="panel-body">
            {subAgents.length === 0 ? (
              <p className="empty">Sub-agent activity will stream here…</p>
            ) : (
              subAgents.map(name => (
                <AgentCard
                  key={name}
                  name={name}
                  sections={agentData[name]?.sections ?? []}
                  isActive={agentData[name]?.isActive ?? false}
                />
              ))
            )}
          </div>
        </section>

        {/* Right: supervisor response */}
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
            {!supervisorText && !isStreaming ? (
              <p className="empty">The supervisor's final answer will appear here…</p>
            ) : (
              <div className="response-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {supervisorText}
                </ReactMarkdown>
                {isStreaming && supervisorText && <span className="cursor">▊</span>}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* ── Error banner ── */}
      {errorMsg && (
        <div className="error-banner">
          ⚠️ {errorMsg}
          <button className="error-close" onClick={() => setErrorMsg('')}>✕</button>
        </div>
      )}

      {/* ── Input bar ── */}
      <footer className="inputbar">
        <textarea
          ref={inputRef}
          className="input-field"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask anything… e.g. 'How many people are in /path/to/image.jpg?' or 'Latest papers on transformers'"
          rows={2}
          disabled={isStreaming}
        />
        <button
          className="send-btn"
          onClick={handleSubmit}
          disabled={isStreaming || !input.trim()}
        >
          {isStreaming ? (
            <span className="spinner" />
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          )}
        </button>
      </footer>
    </div>
  )
}
