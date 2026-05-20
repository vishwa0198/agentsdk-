import { useState, useEffect, useCallback } from 'react'
import SessionSidebar from './components/SessionSidebar.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import ToolCallTrace from './components/ToolCallTrace.jsx'
import TokenCounter from './components/TokenCounter.jsx'
import './index.css'

const AGENT_NAME = 'WebAgent'

export default function App() {
  const [sessions, setSessions] = useState([])
  const [activeSession, setActiveSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [toolCalls, setToolCalls] = useState([])
  const [tokenStats, setTokenStats] = useState({ input: 0, output: 0 })
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [traceOpen, setTraceOpen] = useState(true)

  // ── Session management ────────────────────────────────────────────────
  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`/sessions/${AGENT_NAME}`)
      if (res.ok) setSessions(await res.json())
    } catch {
      // Backend not yet ready; silently ignore.
    }
  }, [])

  useEffect(() => { fetchSessions() }, [fetchSessions])

  const handleNewSession = () => {
    const id = `session-${crypto.randomUUID().slice(0, 8)}`
    setActiveSession(id)
    setMessages([])
    setToolCalls([])
    setTokenStats({ input: 0, output: 0 })
  }

  const handleSelectSession = (sessionId) => {
    if (sessionId === activeSession) return
    setActiveSession(sessionId)
    setMessages([])
    setToolCalls([])
  }

  const handleDeleteSession = async (sessionId) => {
    await fetch(`/sessions/${sessionId}`, { method: 'DELETE' })
    if (activeSession === sessionId) {
      setActiveSession(null)
      setMessages([])
      setToolCalls([])
    }
    fetchSessions()
  }

  // ── WebSocket streaming ───────────────────────────────────────────────
  const handleSend = useCallback(async (text) => {
    if (!activeSession || !text.trim() || isStreaming) return

    setIsStreaming(true)
    setToolCalls([])

    const userMsgId = Date.now()
    const assistantMsgId = userMsgId + 1

    setMessages(prev => [
      ...prev,
      { id: userMsgId, role: 'user', content: text },
    ])

    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${wsProto}//${window.location.host}/ws/${activeSession}`)
    let assistantAdded = false

    ws.onopen = () => {
      ws.send(JSON.stringify({ message: text, agent_name: AGENT_NAME }))
    }

    ws.onmessage = (e) => {
      const event = JSON.parse(e.data)

      if (event.type === 'step') {
        if (!assistantAdded) {
          setMessages(prev => [
            ...prev,
            { id: assistantMsgId, role: 'assistant', content: '', thinking: true, tokens: null },
          ])
          assistantAdded = true
        }
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantMsgId
              ? { ...m, thought: event.data.thought }
              : m,
          ),
        )
      }

      if (event.type === 'tool_call') {
        setToolCalls(prev => [
          ...prev,
          { id: Date.now() + Math.random(), ...event.data, result: null, isError: false },
        ])
      }

      if (event.type === 'tool_result') {
        setToolCalls(prev => {
          const updated = [...prev]
          // Find the last unresolved call with this name and fill in its result.
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].name === event.data.name && updated[i].result === null) {
              updated[i] = { ...updated[i], result: event.data.result, isError: event.data.is_error }
              break
            }
          }
          return updated
        })
      }

      if (event.type === 'final') {
        const tok = event.data.tokens ?? {}
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantMsgId
              ? { ...m, content: event.data.output, thinking: false, tokens: tok }
              : m,
          ),
        )
        setTokenStats(prev => ({
          input: prev.input + (tok.input ?? 0),
          output: prev.output + (tok.output ?? 0),
        }))
        setIsStreaming(false)
        ws.close()
        fetchSessions()
      }

      if (event.type === 'error') {
        if (!assistantAdded) {
          setMessages(prev => [
            ...prev,
            { id: assistantMsgId, role: 'assistant', content: '', thinking: false, tokens: null },
          ])
        }
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantMsgId
              ? { ...m, content: `⚠ ${event.data.message}`, thinking: false, isError: true }
              : m,
          ),
        )
        setIsStreaming(false)
        ws.close()
      }
    }

    ws.onerror = () => {
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantMsgId
            ? { ...m, content: '⚠ Connection error. Please try again.', thinking: false, isError: true }
            : m,
        ),
      )
      setIsStreaming(false)
    }

    ws.onclose = () => setIsStreaming(false)
  }, [activeSession, isStreaming, fetchSessions])

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="app">
      <header className="topbar">
        <button className="icon-btn" onClick={() => setSidebarOpen(o => !o)} title="Toggle sidebar">
          ☰
        </button>
        <span className="topbar-title">agentsdk &mdash; {AGENT_NAME}</span>
        <div className="topbar-right">
          <TokenCounter stats={tokenStats} />
          <button
            className="icon-btn"
            onClick={() => setTraceOpen(o => !o)}
            title="Toggle tool trace"
          >
            🔧
          </button>
        </div>
      </header>

      <div className="main-layout">
        {sidebarOpen && (
          <SessionSidebar
            sessions={sessions}
            activeSession={activeSession}
            onSelect={handleSelectSession}
            onNew={handleNewSession}
            onDelete={handleDeleteSession}
          />
        )}

        <main className="chat-area">
          {activeSession ? (
            <ChatWindow
              messages={messages}
              isStreaming={isStreaming}
              onSend={handleSend}
              sessionId={activeSession}
            />
          ) : (
            <div className="empty-state">
              <p>Select a session or create a new one to start chatting.</p>
              <button className="btn-primary" onClick={handleNewSession}>
                New Session
              </button>
            </div>
          )}
        </main>

        {traceOpen && toolCalls.length > 0 && (
          <aside className="trace-panel">
            <ToolCallTrace toolCalls={toolCalls} />
          </aside>
        )}
      </div>
    </div>
  )
}
