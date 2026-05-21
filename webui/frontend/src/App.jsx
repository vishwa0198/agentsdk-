import { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import SessionSidebar from './components/SessionSidebar.jsx'
import ChatWindow from './components/ChatWindow.jsx'
import ToolCallTrace from './components/ToolCallTrace.jsx'
import TokenCounter from './components/TokenCounter.jsx'
import LoginPage from './pages/LoginPage.jsx'
import AgentConfigPage from './pages/AgentConfigPage.jsx'
import MemoryPage from './pages/MemoryPage.jsx'
import { getMe, getSessions, deleteSession, createWebSocket } from './lib/api.js'
import api from './lib/api.js'
import './index.css'

const queryClient = new QueryClient()

// ---------------------------------------------------------------------------
// Auth guard
// ---------------------------------------------------------------------------
function PrivateRoute({ children }) {
  const token = localStorage.getItem('agentsdk_token')
  return token ? children : <Navigate to="/login" replace />
}

// ---------------------------------------------------------------------------
// Top nav (shown on protected pages)
// ---------------------------------------------------------------------------
function TopNav({ onToggleSidebar, onToggleTrace, tokenStats }) {
  const navigate = useNavigate()
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: () => getMe().then(r => r.data), retry: false })

  const signOut = () => {
    localStorage.removeItem('agentsdk_token')
    queryClient.clear()
    navigate('/login')
  }

  return (
    <header className="topbar">
      <button className="icon-btn hamburger" onClick={onToggleSidebar} title="Toggle sidebar">☰</button>
      <span className="topbar-title">agentsdk</span>
      <nav style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <NavLink to="/" end style={navStyle} className={({ isActive }) => isActive ? 'nav-active' : ''}>Chat</NavLink>
        <NavLink to="/agents" style={navStyle} className={({ isActive }) => isActive ? 'nav-active' : ''}>Agents</NavLink>
        <NavLink to="/memory" style={navStyle} className={({ isActive }) => isActive ? 'nav-active' : ''}>Memory</NavLink>
      </nav>
      <div className="topbar-right">
        <TokenCounter stats={tokenStats} />
        <button className="icon-btn" onClick={onToggleTrace} title="Toggle tool trace">🔧</button>
        <DarkModeToggle />
        {me && (
          <span className="nav-username" style={{ fontSize: 12, padding: '3px 10px', borderRadius: 12, border: '1px solid var(--border)', color: 'var(--text-2)', whiteSpace: 'nowrap' }}>
            {me.username}
          </span>
        )}
        <button className="icon-btn" onClick={signOut} title="Sign out" style={{ fontSize: 12 }}>Sign out</button>
      </div>
    </header>
  )
}

const navStyle = {
  padding: '4px 12px',
  borderRadius: 6,
  fontSize: 13,
  fontWeight: 500,
  color: 'var(--text-1)',
  textDecoration: 'none',
  transition: 'all 0.15s',
}

// ---------------------------------------------------------------------------
// Dark mode toggle
// ---------------------------------------------------------------------------
function DarkModeToggle() {
  const [dark, setDark] = useState(
    () => localStorage.getItem('agentsdk_theme') === 'dark'
      || (!localStorage.getItem('agentsdk_theme')
          && window.matchMedia('(prefers-color-scheme: dark)').matches)
  )

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    localStorage.setItem('agentsdk_theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <button
      className="icon-btn"
      onClick={() => setDark(d => !d)}
      title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {dark ? '☀️' : '🌙'}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Main chat view
// ---------------------------------------------------------------------------
const AGENT_NAME = 'WebAgent'

function ChatView({ sidebarOpen, onCloseSidebar, traceOpen, setTraceOpen, tokenStats, setTokenStats }) {
  const [sessions, setSessions] = useState([])
  const [activeSession, setActiveSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [toolCalls, setToolCalls] = useState([])

  const fetchSessions = useCallback(async () => {
    try {
      const res = await getSessions(AGENT_NAME)
      setSessions(res.data)
    } catch {
      // Backend not yet ready
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
    setTokenStats({ input: 0, output: 0 })
  }

  const handleDeleteSession = async (sessionId) => {
    await deleteSession(sessionId)
    if (activeSession === sessionId) {
      setActiveSession(null)
      setMessages([])
      setToolCalls([])
    }
    fetchSessions()
  }

  const handleSend = useCallback(async (text) => {
    if (!activeSession || !text.trim() || isStreaming) return
    setIsStreaming(true)
    setToolCalls([])

    const userMsgId = Date.now()
    const assistantMsgId = userMsgId + 1

    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: text }])

    const ws = createWebSocket(activeSession)
    let assistantAdded = false

    ws.onopen = () => ws.send(JSON.stringify({ message: text, agent_name: AGENT_NAME }))

    ws.onmessage = (e) => {
      const event = JSON.parse(e.data)

      if (event.type === 'step') {
        if (!assistantAdded) {
          setMessages(prev => [...prev, { id: assistantMsgId, role: 'assistant', content: '', thinking: true, tokens: null }])
          assistantAdded = true
        }
        setMessages(prev => prev.map(m => m.id === assistantMsgId ? { ...m, thought: event.data.thought } : m))
      }

      if (event.type === 'tool_call') {
        setToolCalls(prev => [...prev, { id: Date.now() + Math.random(), ...event.data, result: null, isError: false }])
      }

      if (event.type === 'tool_result') {
        setToolCalls(prev => {
          const updated = [...prev]
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
        setMessages(prev => prev.map(m =>
          m.id === assistantMsgId ? { ...m, content: event.data.output, thinking: false, tokens: tok, animate: true } : m
        ))
        setTokenStats(prev => ({ input: prev.input + (tok.input ?? 0), output: prev.output + (tok.output ?? 0) }))
        setIsStreaming(false)
        ws.close()
        fetchSessions()
      }

      if (event.type === 'error') {
        if (!assistantAdded) setMessages(prev => [...prev, { id: assistantMsgId, role: 'assistant', content: '', thinking: false, tokens: null }])
        setMessages(prev => prev.map(m =>
          m.id === assistantMsgId ? { ...m, content: `⚠ ${event.data.message}`, thinking: false, isError: true } : m
        ))
        setIsStreaming(false)
        ws.close()
      }
    }

    ws.onerror = () => {
      setMessages(prev => prev.map(m =>
        m.id === assistantMsgId ? { ...m, content: '⚠ Connection error. Please try again.', thinking: false, isError: true } : m
      ))
      setIsStreaming(false)
    }

    ws.onclose = () => setIsStreaming(false)
  }, [activeSession, isStreaming, fetchSessions])

  return (
    <div className="main-layout">
      <div className={`sidebar-overlay${sidebarOpen ? ' open' : ''}`} onClick={onCloseSidebar} />
      <SessionSidebar
        isOpen={sidebarOpen}
        sessions={sessions}
        activeSession={activeSession}
        onSelect={handleSelectSession}
        onNew={handleNewSession}
        onDelete={handleDeleteSession}
      />
      <main className="chat-area">
        {activeSession ? (
          <ChatWindow messages={messages} isStreaming={isStreaming} onSend={handleSend} sessionId={activeSession} />
        ) : (
          <div className="empty-state">
            <p>Select a session or create a new one to start chatting.</p>
            <button className="btn-primary" onClick={handleNewSession}>New Session</button>
          </div>
        )}
      </main>
      {traceOpen && toolCalls.length > 0 && (
        <aside className="trace-panel">
          <ToolCallTrace toolCalls={toolCalls} />
        </aside>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Root app with routing
// ---------------------------------------------------------------------------
function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= 768)
  const [traceOpen, setTraceOpen] = useState(true)
  const [tokenStats, setTokenStats] = useState({ input: 0, output: 0 })

  return (
    <div className="app">
      <TopNav
        onToggleSidebar={() => setSidebarOpen(o => !o)}
        onToggleTrace={() => setTraceOpen(o => !o)}
        tokenStats={tokenStats}
      />
      <Routes>
        <Route path="/" element={<ChatView sidebarOpen={sidebarOpen} onCloseSidebar={() => setSidebarOpen(false)} traceOpen={traceOpen} setTraceOpen={setTraceOpen} tokenStats={tokenStats} setTokenStats={setTokenStats} />} />
        <Route path="/agents" element={<AgentConfigPage />} />
        <Route path="/memory" element={<PrivateRoute><MemoryPage /></PrivateRoute>} />
      </Routes>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/*" element={<PrivateRoute><AppShell /></PrivateRoute>} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
