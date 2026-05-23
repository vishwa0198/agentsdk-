import { useState, useEffect, useCallback, useRef } from 'react'
import { getMonitorStats, getMonitorRuns, getMonitorRunDetail } from '../lib/api.js'

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------
function fmtMs(ms) {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const today = new Date()
  if (d.toDateString() === today.toDateString()) return 'Today ' + fmtTime(iso)
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + fmtTime(iso)
}

function fmtTokens(n) {
  if (n == null) return '—'
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

// ---------------------------------------------------------------------------
// Stat Card
// ---------------------------------------------------------------------------
function StatCard({ label, value, sub, color = '#6366f1', icon }) {
  return (
    <div style={{
      background: 'var(--bg-1, #fff)',
      border: '1px solid var(--border)',
      borderRadius: 12,
      padding: '16px 20px',
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {icon && <span style={{ fontSize: 20 }}>{icon}</span>}
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {label}
        </span>
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, color, lineHeight: 1.1 }}>{value ?? '—'}</div>
      {sub && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{sub}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inline bar (CSS-only sparkline)
// ---------------------------------------------------------------------------
function InlineBar({ value, max, color = '#6366f1' }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div style={{ height: 6, borderRadius: 3, background: 'var(--bg-3, #f1f5f9)', overflow: 'hidden', flex: 1 }}>
      <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width 0.4s' }} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------
function StatusBadge({ success, stoppedBy }) {
  if (!success) {
    return <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 10, background: '#fee2e2', color: '#dc2626', fontWeight: 600 }}>error</span>
  }
  if (stoppedBy === 'max_iterations') {
    return <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 10, background: '#fef3c7', color: '#d97706', fontWeight: 600 }}>max iter</span>
  }
  return <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 10, background: '#dcfce7', color: '#16a34a', fontWeight: 600 }}>ok</span>
}

// ---------------------------------------------------------------------------
// Run detail drawer
// ---------------------------------------------------------------------------
function RunDetailDrawer({ runId, onClose }) {
  const [run, setRun] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getMonitorRunDetail(runId)
      .then(r => setRun(r.data))
      .catch(() => setRun(null))
      .finally(() => setLoading(false))
  }, [runId])

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 40,
      display: 'flex', justifyContent: 'flex-end',
    }} onClick={onClose}>
      <div style={{
        width: 420, background: 'var(--bg-1, #fff)', height: '100%',
        overflowY: 'auto', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)',
        padding: 24,
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Run Detail</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--text-2)' }}>✕</button>
        </div>

        {loading ? (
          <div style={{ color: 'var(--text-2)', fontSize: 13 }}>Loading…</div>
        ) : !run ? (
          <div style={{ color: '#ef4444', fontSize: 13 }}>Run not found.</div>
        ) : (
          <>
            {/* Metadata */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 20 }}>
              {[
                ['Run ID', run.run_id],
                ['Session', run.session_id],
                ['Agent', run.agent_name],
                ['Status', <StatusBadge key="s" success={run.success} stoppedBy={run.stopped_by} />],
                ['Started', fmtDate(run.started_at)],
                ['Latency', fmtMs(run.latency_ms)],
                ['Iterations', run.iterations],
                ['Tokens', `${fmtTokens(run.input_tokens)} in / ${fmtTokens(run.output_tokens)} out`],
              ].map(([k, v]) => (
                <div key={k}>
                  <div style={{ fontSize: 11, color: 'var(--text-2)', fontWeight: 600, marginBottom: 2 }}>{k}</div>
                  <div style={{ fontSize: 13 }}>{v}</div>
                </div>
              ))}
            </div>

            {/* Error */}
            {run.error && (
              <div style={{ marginBottom: 16, padding: '10px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, fontSize: 12, color: '#dc2626' }}>
                {run.error}
              </div>
            )}

            {/* Tool call timeline */}
            {run.tool_calls?.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Tool Calls ({run.tool_calls.length})
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {run.tool_calls.map((tc, i) => (
                    <div key={i} style={{
                      padding: '8px 12px', borderRadius: 8,
                      background: 'var(--bg-2, #f8fafc)',
                      border: '1px solid var(--border)',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 10, color: 'var(--text-2)' }}>iter {tc.iteration}</span>
                        <span style={{
                          fontFamily: 'monospace', fontSize: 12, fontWeight: 600,
                          color: '#6366f1', background: '#eef2ff', padding: '1px 7px', borderRadius: 6,
                        }}>
                          {tc.name}
                        </span>
                      </div>
                      {tc.arguments && Object.keys(tc.arguments).length > 0 && (
                        <pre style={{
                          margin: 0, fontSize: 11, color: 'var(--text-2)',
                          fontFamily: 'monospace', overflow: 'auto', maxHeight: 100,
                        }}>
                          {JSON.stringify(tc.arguments, null, 2)}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {run.tool_calls?.length === 0 && (
              <div style={{ fontSize: 13, color: 'var(--text-2)' }}>No tool calls in this run.</div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// MonitorPage
// ---------------------------------------------------------------------------
const REFRESH_INTERVAL = 10_000   // 10 seconds

export default function MonitorPage() {
  const [stats, setStats] = useState(null)
  const [runs, setRuns] = useState([])
  const [selectedRunId, setSelectedRunId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastRefreshed, setLastRefreshed] = useState(null)
  const timerRef = useRef(null)

  const fetchAll = useCallback(async () => {
    setError('')
    try {
      const [statsRes, runsRes] = await Promise.all([
        getMonitorStats(),
        getMonitorRuns(50),
      ])
      setStats(statsRes.data)
      setRuns(runsRes.data)
      setLastRefreshed(new Date())
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  useEffect(() => {
    if (autoRefresh) {
      timerRef.current = setInterval(fetchAll, REFRESH_INTERVAL)
    } else {
      clearInterval(timerRef.current)
    }
    return () => clearInterval(timerRef.current)
  }, [autoRefresh, fetchAll])

  const maxLatency = runs.length > 0 ? Math.max(...runs.map(r => r.latency_ms)) : 1
  const maxTokens = runs.length > 0 ? Math.max(...runs.map(r => r.total_tokens)) : 1

  return (
    <div style={{ padding: '24px 28px', maxWidth: 1100, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0, fontWeight: 700, fontSize: 20 }}>Agent Monitor</h2>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 3 }}>
            Live run stats · auto-refreshes every 10s
            {lastRefreshed && ` · last updated ${fmtTime(lastRefreshed.toISOString())}`}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer', color: 'var(--text-2)' }}>
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
            Auto-refresh
          </label>
          <button onClick={fetchAll} style={{
            padding: '6px 14px', borderRadius: 7, background: '#6366f1', color: '#fff',
            border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600,
          }}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: 16, padding: '10px 14px', borderRadius: 8, background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 14, marginBottom: 28 }}>
        <StatCard icon="🏃" label="Total Runs" value={stats?.total_runs ?? '—'} sub={`${stats?.runs_last_hour ?? 0} in last hour`} color="#6366f1" />
        <StatCard icon="✅" label="Success Rate" value={stats ? `${stats.success_rate}%` : '—'} sub={`${stats?.success_runs ?? 0} ok · ${stats?.error_runs ?? 0} err`} color="#22c55e" />
        <StatCard icon="⏱️" label="Avg Latency" value={fmtMs(stats?.avg_latency_ms)} sub={`p95 ${fmtMs(stats?.p95_latency_ms)}`} color="#f59e0b" />
        <StatCard icon="🪙" label="Total Tokens" value={fmtTokens(stats?.total_tokens)} sub={`${fmtTokens(stats?.total_input_tokens)} in · ${fmtTokens(stats?.total_output_tokens)} out`} color="#0ea5e9" />
        <StatCard icon="🔧" label="Tool Calls" value={stats?.total_tool_calls ?? '—'} sub="across all runs" color="#8b5cf6" />
        <StatCard icon="🖥️" label="Active Sessions" value={stats?.active_sessions ?? '—'} sub="ran in last 5 min" color="#ec4899" />
      </div>

      {/* Top tools */}
      {stats?.top_tools?.length > 0 && (
        <div style={{ marginBottom: 28, background: 'var(--bg-1, #fff)', border: '1px solid var(--border)', borderRadius: 12, padding: '16px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>Top Tools</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {stats.top_tools.map(t => (
              <div key={t.name} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontFamily: 'monospace', fontSize: 12, minWidth: 140, color: '#6366f1' }}>{t.name}</span>
                <InlineBar value={t.count} max={stats.top_tools[0]?.count || 1} color="#6366f1" />
                <span style={{ fontSize: 12, color: 'var(--text-2)', minWidth: 30, textAlign: 'right' }}>{t.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Runs table */}
      <div style={{ background: 'var(--bg-1, #fff)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', fontWeight: 700, fontSize: 13 }}>
          Recent Runs
        </div>

        {loading ? (
          <div style={{ padding: 24, color: 'var(--text-2)', fontSize: 13 }}>Loading…</div>
        ) : runs.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-2)' }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>📭</div>
            No runs recorded yet. Start chatting to see metrics appear here.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: 'var(--bg-2, #f8fafc)' }}>
                {['Time', 'Session', 'Agent', 'Status', 'Iter', 'Latency', 'Tokens', 'Tools'].map(h => (
                  <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: 'var(--text-2)', borderBottom: '1px solid var(--border)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map((run, i) => (
                <tr
                  key={run.run_id}
                  onClick={() => setSelectedRunId(run.run_id)}
                  style={{
                    cursor: 'pointer',
                    background: selectedRunId === run.run_id ? 'var(--bg-2, #f0f4ff)' : i % 2 === 0 ? 'var(--bg-1, #fff)' : 'var(--bg-2, #fafafa)',
                    borderBottom: '1px solid var(--border)',
                    transition: 'background 0.1s',
                  }}
                >
                  <td style={{ padding: '8px 12px', color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{fmtDate(run.started_at)}</td>
                  <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#6366f1', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {run.session_id}
                  </td>
                  <td style={{ padding: '8px 12px' }}>{run.agent_name}</td>
                  <td style={{ padding: '8px 12px' }}>
                    <StatusBadge success={run.success} stoppedBy={run.stopped_by} />
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'center' }}>{run.iterations}</td>
                  <td style={{ padding: '8px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ minWidth: 40 }}>{fmtMs(run.latency_ms)}</span>
                      <InlineBar value={run.latency_ms} max={maxLatency} color="#f59e0b" />
                    </div>
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ minWidth: 40 }}>{fmtTokens(run.total_tokens)}</span>
                      <InlineBar value={run.total_tokens} max={maxTokens} color="#0ea5e9" />
                    </div>
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                    {run.tool_call_count > 0 ? (
                      <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 8, background: '#ede9fe', color: '#7c3aed' }}>
                        {run.tool_call_count}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-2)' }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Run detail drawer */}
      {selectedRunId && (
        <RunDetailDrawer
          runId={selectedRunId}
          onClose={() => setSelectedRunId(null)}
        />
      )}
    </div>
  )
}
