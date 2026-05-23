import { useState, useEffect, useCallback, useRef } from 'react'
import { getSessions, getMemories, searchMemory, deleteMemory, clearMemory, getMemoryStats, ingestMemoryFile } from '../lib/api.js'
import MemoryModal from '../components/MemoryModal.jsx'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const ROLE_ICON = { human: '👤', ai: '🤖', tool_result: '🔧', system: '⚙️' }
const ROLE_LABEL = { human: 'human', ai: 'ai', tool_result: 'tool result', system: 'system' }

function fmtDate(iso) {
  if (!iso) return '—'
  return iso.slice(0, 10)
}

function fmtTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function fmtDateTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })
}

// Count tool_result messages that immediately follow an ai message
function annotateToolCalls(memories) {
  return memories.map((m, i) => {
    if (m.role !== 'ai') return m
    let toolCount = 0
    for (let j = i + 1; j < memories.length; j++) {
      if (memories[j].role === 'tool_result') toolCount++
      else break
    }
    return { ...m, toolCalls: toolCount }
  })
}

// Group array of memories by calendar date (YYYY-MM-DD)
function groupByDate(memories) {
  const groups = {}
  for (const m of memories) {
    const day = fmtDate(m.created_at)
    if (!groups[day]) groups[day] = []
    groups[day].push(m)
  }
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
}

// ---------------------------------------------------------------------------
// Memory card (used in both search results and timeline)
// ---------------------------------------------------------------------------
function MemoryCard({ memory, onViewFull, onDelete, pendingDeleteId, showContent = false }) {
  const [expanded, setExpanded] = useState(showContent)

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '12px 14px',
        background: 'var(--bg-1)',
        marginBottom: 8,
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 15 }}>{ROLE_ICON[memory.role] ?? '💬'}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)', textTransform: 'uppercase', letterSpacing: 0.4 }}>
          {ROLE_LABEL[memory.role] ?? memory.role}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-2)' }}>
          {fmtDate(memory.created_at)} {fmtTime(memory.created_at)}
        </span>
        {memory.toolCalls > 0 && (
          <span style={{
            fontSize: 10, background: 'var(--accent)', color: '#fff',
            borderRadius: 10, padding: '1px 7px', fontWeight: 600,
          }}>
            {memory.toolCalls} tool call{memory.toolCalls > 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Preview / full content */}
      <p
        style={{
          fontSize: 13, color: 'var(--text-0)', margin: 0, lineHeight: 1.5,
          whiteSpace: expanded ? 'pre-wrap' : 'nowrap',
          overflow: expanded ? 'visible' : 'hidden',
          textOverflow: expanded ? 'clip' : 'ellipsis',
          cursor: 'pointer',
        }}
        onClick={() => setExpanded(e => !e)}
        title={expanded ? 'Click to collapse' : 'Click to expand'}
      >
        {expanded ? memory.content : memory.preview}
      </p>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button
          onClick={() => onViewFull(memory)}
          style={btnStyle('secondary')}
        >
          View full
        </button>
        <button
          onClick={() => onDelete(memory)}
          style={btnStyle(pendingDeleteId === memory.id ? 'accent' : 'danger')}
        >
          {pendingDeleteId === memory.id ? 'Confirm?' : 'Delete'}
        </button>
      </div>
    </div>
  )
}

function btnStyle(variant) {
  const base = { fontSize: 12, padding: '3px 10px', borderRadius: 5, cursor: 'pointer', border: 'none', fontWeight: 500 }
  if (variant === 'danger') return { ...base, background: 'rgba(239,68,68,0.12)', color: 'var(--error, #ef4444)' }
  if (variant === 'accent') return { ...base, background: 'var(--accent)', color: '#fff' }
  return { ...base, background: 'var(--bg-3)', color: 'var(--text-1)' }
}

// ---------------------------------------------------------------------------
// Stats bar
// ---------------------------------------------------------------------------
function StatsBar({ stats }) {
  if (!stats) return null
  return (
    <div style={{
      display: 'flex', flexWrap: 'wrap', gap: '8px 20px',
      fontSize: 12, color: 'var(--text-1)', padding: '8px 0',
    }}>
      <StatChip label="Total" value={stats.total_memories} />
      <StatChip label="Human" value={stats.roles?.human ?? 0} />
      <StatChip label="AI" value={stats.roles?.ai ?? 0} />
      <StatChip label="Tool results" value={stats.roles?.tool_result ?? 0} />
      {stats.oldest && (
        <StatChip label="Oldest" value={fmtDateTime(stats.oldest)} />
      )}
      {stats.newest && (
        <StatChip label="Newest" value={fmtDateTime(stats.newest)} />
      )}
    </div>
  )
}

function StatChip({ label, value }) {
  return (
    <span>
      <span style={{ color: 'var(--text-2)' }}>{label}:</span>{' '}
      <strong>{value}</strong>
    </span>
  )
}

// ---------------------------------------------------------------------------
// File drop zone — ingest a file into RAG memory
// ---------------------------------------------------------------------------
function FileDropZone({ sessionId, onIngested }) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [status, setStatus] = useState(null)  // { ok: bool, text: string }
  const inputRef = useRef()

  const ingest = useCallback(async (file) => {
    if (!sessionId) {
      setStatus({ ok: false, text: 'Select a session first.' })
      return
    }
    setUploading(true)
    setStatus(null)
    try {
      const res = await ingestMemoryFile(sessionId, file)
      const d = res.data
      setStatus({
        ok: true,
        text: `Ingested "${d.filename}" — ${d.chars.toLocaleString()} chars in ${d.chunks} chunk${d.chunks !== 1 ? 's' : ''}.`,
      })
      onIngested()
    } catch (err) {
      setStatus({ ok: false, text: err?.response?.data?.detail ?? err.message })
    } finally {
      setUploading(false)
    }
  }, [sessionId, onIngested])

  const onDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) ingest(file)
  }, [ingest])

  const onFileChange = (e) => {
    const file = e.target.files[0]
    if (file) ingest(file)
    e.target.value = ''
  }

  return (
    <div style={{ marginBottom: 20 }}>
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 10,
          padding: '18px 20px',
          background: dragging ? 'rgba(99,102,241,0.06)' : 'var(--bg-1)',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          transition: 'border-color 0.15s, background 0.15s',
        }}
      >
        <span style={{ fontSize: 22 }}>{uploading ? '⏳' : '📎'}</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-0)' }}>
            {uploading ? 'Ingesting…' : 'Ingest file into memory'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>
            Drop a .txt, .pdf, .md, .py, .json, .csv file — or click to browse
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".txt,.md,.pdf,.csv,.py,.js,.ts,.json,.yaml,.yml,.rst,.log"
          style={{ display: 'none' }}
          onChange={onFileChange}
        />
      </div>
      {status && (
        <div style={{
          marginTop: 8,
          padding: '8px 12px',
          borderRadius: 6,
          fontSize: 12,
          background: status.ok ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
          color: status.ok ? '#16a34a' : 'var(--error, #ef4444)',
          border: `1px solid ${status.ok ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}`,
        }}>
          {status.ok ? '✓ ' : '✗ '}{status.text}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function MemoryPage() {
  const [sessions, setSessions] = useState([])
  const [selectedSession, setSelectedSession] = useState('')
  const [memories, setMemories] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Search
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [searching, setSearching] = useState(false)

  // Modal
  const [modalMemory, setModalMemory] = useState(null)

  // Inline confirmation
  const [pendingDeleteId, setPendingDeleteId] = useState(null)
  const [clearConfirm, setClearConfirm] = useState(false)

  // ── load sessions on mount ──────────────────────────────────────────────
  useEffect(() => {
    getSessions('WebAgent')
      .then(r => {
        setSessions(r.data)
        if (r.data.length > 0) setSelectedSession(r.data[0].session_id)
      })
      .catch(() => {})
  }, [])

  // ── load memories when session changes ────────────────────────────────
  const loadMemories = useCallback(async (sessionId) => {
    if (!sessionId) return
    setLoading(true)
    setError('')
    setSearchResults(null)
    setSearchQuery('')
    try {
      const [memRes, statsRes] = await Promise.all([
        getMemories(sessionId),
        getMemoryStats(sessionId),
      ])
      setMemories(memRes.data.memories ?? [])
      setStats(statsRes.data)
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Failed to load memories')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectedSession) loadMemories(selectedSession)
  }, [selectedSession, loadMemories])

  // ── search ─────────────────────────────────────────────────────────────
  const handleSearch = async (e) => {
    e.preventDefault()
    if (!searchQuery.trim() || !selectedSession) return
    setSearching(true)
    try {
      const res = await searchMemory(selectedSession, searchQuery.trim())
      setSearchResults(res.data.results ?? [])
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  // ── delete single ──────────────────────────────────────────────────────
  const handleDelete = async (memory) => {
    if (pendingDeleteId !== memory.id) { setPendingDeleteId(memory.id); return }
    setPendingDeleteId(null)
    try {
      await deleteMemory(selectedSession, memory.id)
      await loadMemories(selectedSession)
      if (searchResults) {
        setSearchResults(prev =>
          prev.filter(r => r.created_at !== memory.created_at || r.content !== memory.content)
        )
      }
    } catch {
      // silently ignore
    }
  }

  // ── clear all ──────────────────────────────────────────────────────────
  const handleClearAll = async () => {
    if (!clearConfirm) { setClearConfirm(true); return }
    setClearConfirm(false)
    try {
      await clearMemory(selectedSession)
      setMemories([])
      setStats(null)
      setSearchResults(null)
    } catch {
      // silently ignore
    }
  }

  // ── derived ─────────────────────────────────────────────────────────────
  const annotated = annotateToolCalls(memories)
  const dateGroups = groupByDate(annotated)

  // ────────────────────────────────────────────────────────────────────────
  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '24px 16px', position: 'relative' }}>

      {/* Modal overlay anchored to page */}
      {modalMemory && (
        <MemoryModal memory={modalMemory} onClose={() => setModalMemory(null)} />
      )}

      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 20, color: 'var(--text-0)' }}>
        Memory Visualiser
      </h1>

      {/* ── Section 1: Session selector + stats ─────────────────────────── */}
      <div style={{
        background: 'var(--bg-1)', borderRadius: 10, padding: '16px 18px',
        marginBottom: 20, border: '1px solid var(--border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', whiteSpace: 'nowrap' }}>Session:</label>
          <select
            value={selectedSession}
            onChange={e => setSelectedSession(e.target.value)}
            style={{
              flex: 1, minWidth: 180, padding: '6px 10px', borderRadius: 6,
              border: '1px solid var(--border)', background: 'var(--bg-2)',
              color: 'var(--text-0)', fontSize: 13,
            }}
          >
            <option value="">— select a session —</option>
            {sessions.map(s => (
              <option key={s.session_id} value={s.session_id}>{s.session_id}</option>
            ))}
          </select>
          {selectedSession && (
            <button
              onClick={handleClearAll}
              style={{
                padding: '6px 14px', borderRadius: 6, fontSize: 13,
                background: 'rgba(239,68,68,0.12)', color: 'var(--error, #ef4444)',
                border: '1px solid rgba(239,68,68,0.3)', cursor: 'pointer', fontWeight: 500,
                whiteSpace: 'nowrap',
              }}
            >
              {clearConfirm ? 'Confirm clear?' : 'Clear all memory'}
            </button>
          )}
        </div>

        {stats && <StatsBar stats={stats} />}
      </div>

      {error && (
        <div style={{ color: 'var(--error, #ef4444)', background: 'rgba(239,68,68,0.08)', borderRadius: 6, padding: '10px 14px', marginBottom: 16, fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* ── Section 2: File ingest ───────────────────────────────────────── */}
      <FileDropZone
        sessionId={selectedSession}
        onIngested={() => loadMemories(selectedSession)}
      />

      {/* ── Section 3: Semantic search ───────────────────────────────────── */}
      <div style={{
        background: 'var(--bg-1)', borderRadius: 10, padding: '16px 18px',
        marginBottom: 20, border: '1px solid var(--border)',
      }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, color: 'var(--text-0)' }}>
          Semantic Search
        </h2>
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search memories…"
            disabled={!selectedSession}
            style={{
              flex: 1, padding: '8px 12px', borderRadius: 6,
              border: '1px solid var(--border)', background: 'var(--bg-2)',
              color: 'var(--text-0)', fontSize: 13,
            }}
          />
          <button
            type="submit"
            disabled={!selectedSession || searching || !searchQuery.trim()}
            style={{ ...btnStyle('accent'), padding: '8px 18px', fontSize: 13 }}
          >
            {searching ? '…' : 'Search'}
          </button>
          {searchResults !== null && (
            <button
              type="button"
              onClick={() => { setSearchResults(null); setSearchQuery('') }}
              style={{ ...btnStyle('secondary'), padding: '8px 12px', fontSize: 13 }}
            >
              Clear
            </button>
          )}
        </form>

        {searchResults !== null && (
          <div style={{ marginTop: 14 }}>
            <p style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10 }}>
              {searchResults.length === 0
                ? `No results for "${searchQuery}"`
                : `${searchResults.length} result${searchResults.length > 1 ? 's' : ''} for "${searchQuery}"`}
            </p>
            {searchResults.map((r, i) => (
              <MemoryCard
                key={i}
                memory={{ ...r, id: String(i) }}
                onViewFull={setModalMemory}
                onDelete={handleDelete}
                pendingDeleteId={pendingDeleteId}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Section 3: Timeline ─────────────────────────────────────────── */}
      <div style={{
        background: 'var(--bg-1)', borderRadius: 10, padding: '16px 18px',
        border: '1px solid var(--border)',
      }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, color: 'var(--text-0)' }}>
          Full Memory Timeline
          {memories.length > 0 && (
            <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-2)', fontWeight: 400 }}>
              ({memories.length} entr{memories.length === 1 ? 'y' : 'ies'})
            </span>
          )}
        </h2>

        {loading && (
          <p style={{ color: 'var(--text-2)', fontSize: 13 }}>Loading…</p>
        )}

        {!loading && memories.length === 0 && selectedSession && (
          <p style={{ color: 'var(--text-2)', fontSize: 13 }}>
            No memories stored for this session yet.
          </p>
        )}

        {!loading && !selectedSession && (
          <p style={{ color: 'var(--text-2)', fontSize: 13 }}>
            Select a session above to view its memory timeline.
          </p>
        )}

        {dateGroups.map(([date, entries]) => (
          <div key={date}>
            {/* Date divider */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              margin: '16px 0 10px', color: 'var(--text-2)',
            }}>
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.5, whiteSpace: 'nowrap' }}>
                {new Date(date + 'T00:00:00').toLocaleDateString([], { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
              </span>
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            </div>

            {entries.map(m => (
              <MemoryCard
                key={m.id}
                memory={m}
                onViewFull={setModalMemory}
                onDelete={handleDelete}
                pendingDeleteId={pendingDeleteId}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
