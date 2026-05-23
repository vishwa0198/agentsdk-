import { useState, useEffect, useCallback } from 'react'
import { getMCPServers, addMCPServer, removeMCPServer, connectMCPServer, disconnectMCPServer } from '../lib/api.js'

// ---------------------------------------------------------------------------
// Transport badge
// ---------------------------------------------------------------------------
const TRANSPORT_COLOR = { stdio: '#6366f1', sse: '#0ea5e9', http: '#10b981' }
const TRANSPORT_ICON = { stdio: '⚙️', sse: '📡', http: '🌐' }

function TransportBadge({ transport }) {
  return (
    <span style={{
      fontSize: 11,
      fontWeight: 600,
      padding: '2px 8px',
      borderRadius: 20,
      background: TRANSPORT_COLOR[transport] ?? '#888',
      color: '#fff',
      letterSpacing: '0.04em',
    }}>
      {TRANSPORT_ICON[transport]} {transport.toUpperCase()}
    </span>
  )
}

// ---------------------------------------------------------------------------
// ToolChip
// ---------------------------------------------------------------------------
function ToolChip({ name }) {
  return (
    <span style={{
      display: 'inline-block',
      fontSize: 11,
      padding: '2px 8px',
      borderRadius: 12,
      background: 'var(--bg-3, #f3f4f6)',
      color: 'var(--text-2, #555)',
      border: '1px solid var(--border)',
      fontFamily: 'monospace',
    }}>
      {name}
    </span>
  )
}

// ---------------------------------------------------------------------------
// AddServerForm
// ---------------------------------------------------------------------------
const EMPTY_FORM = {
  name: '',
  transport: 'stdio',
  command: '',
  args: '',   // space-separated, split on submit
  url: '',
}

function AddServerForm({ onAdd, onCancel }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!form.name.trim()) { setError('Name is required'); return }
    if (form.transport === 'stdio' && !form.command.trim()) { setError('Command is required for stdio'); return }
    if ((form.transport === 'sse' || form.transport === 'http') && !form.url.trim()) { setError('URL is required for ' + form.transport); return }

    const body = {
      name: form.name.trim(),
      transport: form.transport,
      command: form.transport === 'stdio' ? form.command.trim() || null : null,
      args: form.transport === 'stdio' ? form.args.trim().split(/\s+/).filter(Boolean) : [],
      url: form.transport !== 'stdio' ? form.url.trim() || null : null,
    }

    setLoading(true)
    try {
      await onAdd(body)
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message)
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = {
    width: '100%',
    padding: '7px 10px',
    borderRadius: 6,
    border: '1px solid var(--border)',
    background: 'var(--bg-2, #f9fafb)',
    color: 'var(--text-1)',
    fontSize: 13,
    boxSizing: 'border-box',
  }

  return (
    <form onSubmit={handleSubmit} style={{
      background: 'var(--bg-2, #f9fafb)',
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: 20,
      marginBottom: 20,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 14, fontSize: 14 }}>Add MCP Server</div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-2)' }}>
          Name *
          <input style={inputStyle} value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. filesystem" />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-2)' }}>
          Transport *
          <select style={inputStyle} value={form.transport} onChange={e => set('transport', e.target.value)}>
            <option value="stdio">stdio (local subprocess)</option>
            <option value="sse">sse (HTTP/SSE)</option>
            <option value="http">http (Streamable HTTP)</option>
          </select>
        </label>
      </div>

      {form.transport === 'stdio' ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12, marginBottom: 12 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-2)' }}>
            Command *
            <input style={inputStyle} value={form.command} onChange={e => set('command', e.target.value)} placeholder="npx" />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-2)' }}>
            Arguments (space-separated)
            <input style={inputStyle} value={form.args} onChange={e => set('args', e.target.value)} placeholder="-y @modelcontextprotocol/server-filesystem /tmp" />
          </label>
        </div>
      ) : (
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-2)', marginBottom: 12 }}>
          URL *
          <input style={inputStyle} value={form.url} onChange={e => set('url', e.target.value)} placeholder="http://localhost:8080/sse" />
        </label>
      )}

      {error && <div style={{ color: '#ef4444', fontSize: 12, marginBottom: 10 }}>{error}</div>}

      <div style={{ display: 'flex', gap: 8 }}>
        <button type="submit" disabled={loading} style={{
          padding: '7px 18px', borderRadius: 6, background: '#6366f1', color: '#fff',
          border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 500,
          opacity: loading ? 0.6 : 1,
        }}>
          {loading ? 'Adding…' : 'Add Server'}
        </button>
        <button type="button" onClick={onCancel} style={{
          padding: '7px 18px', borderRadius: 6, background: 'transparent',
          border: '1px solid var(--border)', cursor: 'pointer', fontSize: 13,
          color: 'var(--text-2)',
        }}>
          Cancel
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// ServerCard
// ---------------------------------------------------------------------------
function ServerCard({ server, onConnect, onDisconnect, onRemove }) {
  const [loadingConnect, setLoadingConnect] = useState(false)
  const [pendingRemove, setPendingRemove] = useState(false)

  const handleConnect = async () => {
    setLoadingConnect(true)
    try { await onConnect(server.id) } finally { setLoadingConnect(false) }
  }

  const handleDisconnect = async () => {
    setLoadingConnect(true)
    try { await onDisconnect(server.id) } finally { setLoadingConnect(false) }
  }

  const cardStyle = {
    border: `1px solid ${server.connected ? '#22c55e' : 'var(--border)'}`,
    borderRadius: 10,
    padding: 16,
    background: 'var(--bg-1, #fff)',
    transition: 'border-color 0.2s',
  }

  return (
    <div style={cardStyle}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <div style={{
          width: 10, height: 10, borderRadius: '50%',
          background: server.connected ? '#22c55e' : '#d1d5db',
          flexShrink: 0,
        }} />
        <span style={{ fontWeight: 600, fontSize: 14, flex: 1 }}>{server.name}</span>
        <TransportBadge transport={server.transport} />
      </div>

      {/* Connection details */}
      <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10, fontFamily: 'monospace' }}>
        {server.transport === 'stdio'
          ? `${server.command ?? ''} ${(server.args ?? []).join(' ')}`
          : server.url ?? ''}
      </div>

      {/* Error */}
      {server.error && (
        <div style={{ fontSize: 12, color: '#ef4444', marginBottom: 10, padding: '6px 10px', background: '#fef2f2', borderRadius: 6 }}>
          {server.error}
        </div>
      )}

      {/* Tools */}
      {server.connected && server.tool_names?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 6, fontWeight: 600 }}>
            {server.tool_count} TOOL{server.tool_count !== 1 ? 'S' : ''}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {server.tool_names.map(name => <ToolChip key={name} name={name} />)}
          </div>
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {!server.connected ? (
          <button onClick={handleConnect} disabled={loadingConnect} style={{
            padding: '5px 14px', borderRadius: 6, background: '#22c55e', color: '#fff',
            border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 500,
            opacity: loadingConnect ? 0.6 : 1,
          }}>
            {loadingConnect ? 'Connecting…' : 'Connect'}
          </button>
        ) : (
          <button onClick={handleDisconnect} disabled={loadingConnect} style={{
            padding: '5px 14px', borderRadius: 6, background: '#f59e0b', color: '#fff',
            border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 500,
            opacity: loadingConnect ? 0.6 : 1,
          }}>
            {loadingConnect ? '…' : 'Disconnect'}
          </button>
        )}

        {!pendingRemove ? (
          <button onClick={() => setPendingRemove(true)} style={{
            padding: '5px 14px', borderRadius: 6, background: 'transparent',
            border: '1px solid var(--border)', cursor: 'pointer', fontSize: 12, color: 'var(--text-2)',
          }}>
            Remove
          </button>
        ) : (
          <>
            <button onClick={() => onRemove(server.id)} style={{
              padding: '5px 14px', borderRadius: 6, background: '#ef4444', color: '#fff',
              border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 500,
            }}>
              Confirm
            </button>
            <button onClick={() => setPendingRemove(false)} style={{
              padding: '5px 14px', borderRadius: 6, background: 'transparent',
              border: '1px solid var(--border)', cursor: 'pointer', fontSize: 12, color: 'var(--text-2)',
            }}>
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// MCPPage
// ---------------------------------------------------------------------------
export default function MCPPage() {
  const [servers, setServers] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')

  const fetchServers = useCallback(async () => {
    try {
      const res = await getMCPServers()
      setServers(res.data)
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchServers() }, [fetchServers])

  const handleAdd = async (body) => {
    await addMCPServer(body)
    setShowForm(false)
    await fetchServers()
  }

  const handleConnect = async (serverId) => {
    setError('')
    try {
      await connectMCPServer(serverId)
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message)
    } finally {
      await fetchServers()
    }
  }

  const handleDisconnect = async (serverId) => {
    await disconnectMCPServer(serverId)
    await fetchServers()
  }

  const handleRemove = async (serverId) => {
    await removeMCPServer(serverId)
    setServers(prev => prev.filter(s => s.id !== serverId))
  }

  const connectedCount = servers.filter(s => s.connected).length
  const totalTools = servers.reduce((sum, s) => sum + (s.tool_count ?? 0), 0)

  return (
    <div style={{ padding: '24px 28px', maxWidth: 800, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontWeight: 700, fontSize: 20 }}>MCP Servers</h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-2)' }}>
            Connect external tool servers via Model Context Protocol
          </p>
        </div>
        <button onClick={() => setShowForm(v => !v)} style={{
          padding: '8px 18px', borderRadius: 8, background: '#6366f1', color: '#fff',
          border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600,
        }}>
          {showForm ? '✕ Cancel' : '+ Add Server'}
        </button>
      </div>

      {/* Stats bar */}
      {servers.length > 0 && (
        <div style={{
          display: 'flex', gap: 20, marginBottom: 20, padding: '12px 16px',
          background: 'var(--bg-2)', borderRadius: 8, border: '1px solid var(--border)',
          fontSize: 13,
        }}>
          <span><strong>{servers.length}</strong> server{servers.length !== 1 ? 's' : ''}</span>
          <span style={{ color: '#22c55e' }}><strong>{connectedCount}</strong> connected</span>
          <span style={{ color: '#6366f1' }}><strong>{totalTools}</strong> tool{totalTools !== 1 ? 's' : ''} available</span>
        </div>
      )}

      {/* Global error */}
      {error && (
        <div style={{
          marginBottom: 16, padding: '10px 14px', borderRadius: 8,
          background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', fontSize: 13,
        }}>
          {error}
          <button onClick={() => setError('')} style={{ marginLeft: 10, background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', fontSize: 16 }}>✕</button>
        </div>
      )}

      {/* Add form */}
      {showForm && <AddServerForm onAdd={handleAdd} onCancel={() => setShowForm(false)} />}

      {/* Server list */}
      {loading ? (
        <div style={{ color: 'var(--text-2)', fontSize: 14, paddingTop: 20 }}>Loading…</div>
      ) : servers.length === 0 ? (
        <div style={{
          padding: '48px 24px', textAlign: 'center', border: '2px dashed var(--border)',
          borderRadius: 12, color: 'var(--text-2)',
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🔌</div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>No MCP servers yet</div>
          <div style={{ fontSize: 13 }}>
            Add a server above to give your agent access to tools from any MCP-compatible server.<br />
            Try <code>npx @modelcontextprotocol/server-filesystem /tmp</code> to get started.
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {servers.map(server => (
            <ServerCard
              key={server.id}
              server={server}
              onConnect={handleConnect}
              onDisconnect={handleDisconnect}
              onRemove={handleRemove}
            />
          ))}
        </div>
      )}

      {/* Quick start examples */}
      {servers.length === 0 && !showForm && (
        <div style={{ marginTop: 32 }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10, color: 'var(--text-2)' }}>QUICK START EXAMPLES</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { name: 'Filesystem', transport: 'stdio', cmd: 'npx -y @modelcontextprotocol/server-filesystem /tmp' },
              { name: 'Brave Search', transport: 'stdio', cmd: 'npx -y @modelcontextprotocol/server-brave-search' },
              { name: 'Postgres', transport: 'stdio', cmd: 'npx -y @modelcontextprotocol/server-postgres postgresql://localhost/mydb' },
            ].map(ex => (
              <div key={ex.name} style={{
                padding: '10px 14px', borderRadius: 8, border: '1px solid var(--border)',
                display: 'flex', alignItems: 'center', gap: 12, fontSize: 12,
              }}>
                <TransportBadge transport={ex.transport} />
                <span style={{ fontWeight: 600 }}>{ex.name}</span>
                <code style={{ color: 'var(--text-2)', fontFamily: 'monospace', fontSize: 11 }}>{ex.cmd}</code>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
