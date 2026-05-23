import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

const ALL_COMMANDS = [
  { id: 'nav-chat',     section: 'Navigate', icon: '💬', title: 'Chat',          sub: '/',          type: 'nav', to: '/' },
  { id: 'nav-agents',   section: 'Navigate', icon: '🤖', title: 'Agents',        sub: '/agents',    type: 'nav', to: '/agents' },
  { id: 'nav-memory',   section: 'Navigate', icon: '🧠', title: 'Memory',        sub: '/memory',    type: 'nav', to: '/memory' },
  { id: 'nav-mcp',      section: 'Navigate', icon: '🔌', title: 'MCP Servers',   sub: '/mcp',       type: 'nav', to: '/mcp' },
  { id: 'nav-pipeline', section: 'Navigate', icon: '🔗', title: 'Pipeline',      sub: '/pipeline',  type: 'nav', to: '/pipeline' },
  { id: 'nav-monitor',  section: 'Navigate', icon: '📊', title: 'Monitor',       sub: '/monitor',   type: 'nav', to: '/monitor' },
  { id: 'nav-schedule', section: 'Navigate', icon: '⏰', title: 'Schedules',     sub: '/schedule',  type: 'nav', to: '/schedule' },
  { id: 'act-theme',    section: 'Actions',  icon: '🌙', title: 'Toggle Dark Mode', sub: '',        type: 'action', action: 'theme' },
  { id: 'act-signout',  section: 'Actions',  icon: '🚪', title: 'Sign Out',         sub: '',        type: 'action', action: 'signout' },
]

export default function CommandPalette({ onClose }) {
  const [query, setQuery]     = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const navigate   = useNavigate()
  const inputRef   = useRef(null)

  // Auto-focus input on mount
  useEffect(() => { inputRef.current?.focus() }, [])

  // Close on Escape
  useEffect(() => {
    const onEsc = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onEsc)
    return () => window.removeEventListener('keydown', onEsc)
  }, [onClose])

  const q = query.toLowerCase().trim()
  const filtered = q
    ? ALL_COMMANDS.filter(c =>
        c.title.toLowerCase().includes(q) || c.sub.toLowerCase().includes(q)
      )
    : ALL_COMMANDS

  // Reset active index when query changes
  useEffect(() => { setActiveIdx(0) }, [query])

  const execute = useCallback((cmd) => {
    onClose()
    if (cmd.type === 'nav') {
      navigate(cmd.to)
    } else if (cmd.action === 'theme') {
      const dark = document.documentElement.getAttribute('data-theme') === 'dark'
      document.documentElement.setAttribute('data-theme', dark ? 'light' : 'dark')
      localStorage.setItem('agentsdk_theme', dark ? 'light' : 'dark')
    } else if (cmd.action === 'signout') {
      localStorage.removeItem('agentsdk_token')
      navigate('/login')
    }
  }, [onClose, navigate])

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (filtered[activeIdx]) execute(filtered[activeIdx])
    }
  }

  // Group commands by section for display
  const grouped = {}
  filtered.forEach(cmd => {
    if (!grouped[cmd.section]) grouped[cmd.section] = []
    grouped[cmd.section].push(cmd)
  })

  return (
    <div className="cmd-overlay" onMouseDown={onClose}>
      <div className="cmd-box" onMouseDown={e => e.stopPropagation()}>

        {/* Search input row */}
        <div className="cmd-input-row">
          <span className="cmd-icon">⌘</span>
          <input
            ref={inputRef}
            className="cmd-input"
            placeholder="Type a command or page name…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            autoComplete="off"
            spellCheck={false}
          />
          <span className="cmd-kbd">esc</span>
        </div>

        {/* Results list */}
        <div className="cmd-list">
          {filtered.length === 0 ? (
            <div className="cmd-empty">No matching commands</div>
          ) : (
            Object.entries(grouped).map(([section, items]) => (
              <div key={section}>
                <div className="cmd-section-label">{section}</div>
                {items.map(cmd => {
                  const idx = filtered.indexOf(cmd)
                  return (
                    <button
                      key={cmd.id}
                      className={`cmd-item${idx === activeIdx ? ' cmd-active' : ''}`}
                      onMouseDown={() => execute(cmd)}
                      onMouseEnter={() => setActiveIdx(idx)}
                    >
                      <span className="cmd-item-icon">{cmd.icon}</span>
                      <div className="cmd-item-text">
                        <div className="cmd-item-title">{cmd.title}</div>
                        {cmd.sub && <div className="cmd-item-sub">{cmd.sub}</div>}
                      </div>
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer hints */}
        <div className="cmd-footer">
          <span className="cmd-footer-item"><span className="cmd-kbd">↑↓</span> navigate</span>
          <span className="cmd-footer-item"><span className="cmd-kbd">↵</span> select</span>
          <span className="cmd-footer-item"><span className="cmd-kbd">esc</span> close</span>
        </div>
      </div>
    </div>
  )
}
