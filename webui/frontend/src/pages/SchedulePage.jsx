import { useState, useEffect, useCallback } from 'react'
import {
  listSchedules, createSchedule, deleteSchedule,
  enableSchedule, disableSchedule, runScheduleNow,
} from '../lib/api.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const today = new Date()
  if (d.toDateString() === today.toDateString())
    return 'Today ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function TriggerBadge({ schedule }) {
  const label = schedule.trigger_type === 'interval'
    ? `every ${_fmtInterval(schedule.interval_seconds)}`
    : `cron: ${schedule.cron}`
  return (
    <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 8, background: '#ede9fe', color: '#7c3aed', fontWeight: 600 }}>
      ⏱ {label}
    </span>
  )
}

function StatusDot({ ok }) {
  if (ok === null || ok === undefined) return <span style={{ color: 'var(--text-2)', fontSize: 12 }}>—</span>
  return ok
    ? <span style={{ color: '#22c55e', fontSize: 14 }}>✓</span>
    : <span style={{ color: '#ef4444', fontSize: 14 }}>✗</span>
}

function _fmtInterval(sec) {
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.round(sec / 60)}m`
  if (sec < 86400) return `${Math.round(sec / 3600)}h`
  return `${Math.round(sec / 86400)}d`
}

// ---------------------------------------------------------------------------
// Create-schedule form
// ---------------------------------------------------------------------------
const DEFAULT_FORM = {
  name: '',
  agent_name: 'WebAgent',
  input_message: '',
  trigger_type: 'interval',
  interval_seconds: 3600,
  cron: '0 * * * *',
  enabled: true,
}

function CreateForm({ onCreated, onCancel }) {
  const [form, setForm] = useState(DEFAULT_FORM)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }))

  const submit = async (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.input_message.trim()) {
      setError('Name and input message are required.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const res = await createSchedule({
        ...form,
        interval_seconds: Number(form.interval_seconds),
      })
      onCreated(res.data)
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message)
    } finally {
      setSaving(false)
    }
  }

  const inp = { background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 7, padding: '6px 10px', fontSize: 13, color: 'var(--text-1)', width: '100%', boxSizing: 'border-box' }

  return (
    <form onSubmit={submit} style={{
      background: 'var(--bg-1)', border: '1px solid var(--border)',
      borderRadius: 12, padding: 20, marginBottom: 24,
    }}>
      <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 16 }}>New Schedule</div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        <label>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-2)', marginBottom: 4 }}>SCHEDULE NAME</div>
          <input style={inp} value={form.name} onChange={e => set('name', e.target.value)} placeholder="Daily digest" required />
        </label>
        <label>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-2)', marginBottom: 4 }}>AGENT</div>
          <input style={inp} value={form.agent_name} onChange={e => set('agent_name', e.target.value)} placeholder="WebAgent" />
        </label>
      </div>

      <label style={{ display: 'block', marginBottom: 12 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-2)', marginBottom: 4 }}>INPUT MESSAGE (sent to agent)</div>
        <textarea
          style={{ ...inp, resize: 'vertical', minHeight: 60 }}
          value={form.input_message}
          onChange={e => set('input_message', e.target.value)}
          placeholder="Summarize the latest news and report key updates."
          required
        />
      </label>

      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13 }}>
          <input type="radio" checked={form.trigger_type === 'interval'} onChange={() => set('trigger_type', 'interval')} />
          Interval
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13 }}>
          <input type="radio" checked={form.trigger_type === 'cron'} onChange={() => set('trigger_type', 'cron')} />
          Cron
        </label>
      </div>

      {form.trigger_type === 'interval' ? (
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-2)', marginBottom: 4 }}>INTERVAL (seconds)</div>
          <input type="number" style={{ ...inp, width: 160 }} min={10} value={form.interval_seconds}
            onChange={e => set('interval_seconds', e.target.value)} />
          <span style={{ fontSize: 12, color: 'var(--text-2)', marginLeft: 8 }}>
            = {_fmtInterval(Number(form.interval_seconds))}
          </span>
        </label>
      ) : (
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-2)', marginBottom: 4 }}>CRON EXPRESSION (5-field)</div>
          <input style={{ ...inp, width: 200, fontFamily: 'monospace' }} value={form.cron}
            onChange={e => set('cron', e.target.value)} placeholder="0 * * * *" />
          <span style={{ fontSize: 11, color: 'var(--text-2)', marginLeft: 8 }}>min hour day month weekday</span>
        </label>
      )}

      {error && <div style={{ color: '#ef4444', fontSize: 12, marginBottom: 10 }}>{error}</div>}

      <div style={{ display: 'flex', gap: 8 }}>
        <button type="submit" disabled={saving} style={{
          padding: '7px 18px', borderRadius: 7, background: '#6366f1',
          color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 13,
        }}>
          {saving ? 'Creating…' : 'Create Schedule'}
        </button>
        <button type="button" onClick={onCancel} style={{
          padding: '7px 14px', borderRadius: 7, background: 'var(--bg-2)',
          border: '1px solid var(--border)', cursor: 'pointer', fontSize: 13,
        }}>
          Cancel
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Schedule card
// ---------------------------------------------------------------------------
function ScheduleCard({ schedule, onRefresh }) {
  const [running, setRunning] = useState(false)
  const [toggling, setToggling] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [lastResult, setLastResult] = useState(null)
  const webhookUrl = `${window.location.protocol}//${window.location.hostname}:8000/webhook/${schedule.webhook_token}`

  const handleRun = async () => {
    setRunning(true)
    setLastResult(null)
    try {
      const res = await runScheduleNow(schedule.id)
      setLastResult(res.data)
    } catch (err) {
      setLastResult({ success: false, error: err.response?.data?.detail ?? err.message })
    } finally {
      setRunning(false)
      onRefresh()
    }
  }

  const handleToggle = async () => {
    setToggling(true)
    try {
      if (schedule.enabled) await disableSchedule(schedule.id)
      else await enableSchedule(schedule.id)
      onRefresh()
    } finally {
      setToggling(false)
    }
  }

  const handleDelete = async () => {
    try {
      await deleteSchedule(schedule.id)
      onRefresh()
    } catch {}
    setConfirming(false)
  }

  return (
    <div style={{
      background: 'var(--bg-1)', border: '1px solid var(--border)', borderRadius: 12,
      padding: 18, marginBottom: 12,
      opacity: schedule.enabled ? 1 : 0.65,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, flexWrap: 'wrap' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ fontWeight: 700, fontSize: 14 }}>{schedule.name}</span>
            <span style={{
              fontSize: 10, padding: '1px 7px', borderRadius: 8,
              background: schedule.enabled ? '#dcfce7' : '#f1f5f9',
              color: schedule.enabled ? '#16a34a' : 'var(--text-2)',
              fontWeight: 700, textTransform: 'uppercase',
            }}>
              {schedule.enabled ? 'active' : 'paused'}
            </span>
            <TriggerBadge schedule={schedule} />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 4 }}>
            <b>Agent:</b> {schedule.agent_name} · <b>Message:</b> {schedule.input_message.substring(0, 80)}{schedule.input_message.length > 80 ? '…' : ''}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
            <b>Last run:</b> {fmtTime(schedule.last_run_at)} &nbsp;
            <StatusDot ok={schedule.last_run_ok} />
            {schedule.last_output && <span style={{ marginLeft: 8, color: 'var(--text-1)' }}>{schedule.last_output.substring(0, 60)}…</span>}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <button onClick={handleRun} disabled={running} title="Run now" style={{
            padding: '5px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600,
            background: '#6366f1', color: '#fff', border: 'none', cursor: 'pointer',
          }}>
            {running ? '⏳' : '▶ Run now'}
          </button>
          <button onClick={handleToggle} disabled={toggling} style={{
            padding: '5px 10px', borderRadius: 6, fontSize: 12,
            background: 'var(--bg-2)', border: '1px solid var(--border)', cursor: 'pointer',
          }}>
            {schedule.enabled ? '⏸ Pause' : '▶ Resume'}
          </button>
          {confirming ? (
            <>
              <button onClick={handleDelete} style={{
                padding: '5px 10px', borderRadius: 6, fontSize: 12,
                background: '#fee2e2', color: '#dc2626', border: '1px solid #fca5a5', cursor: 'pointer', fontWeight: 600,
              }}>Confirm delete</button>
              <button onClick={() => setConfirming(false)} style={{
                padding: '5px 10px', borderRadius: 6, fontSize: 12,
                background: 'var(--bg-2)', border: '1px solid var(--border)', cursor: 'pointer',
              }}>Cancel</button>
            </>
          ) : (
            <button onClick={() => setConfirming(true)} title="Delete" style={{
              padding: '5px 10px', borderRadius: 6, fontSize: 12,
              background: 'var(--bg-2)', border: '1px solid var(--border)', cursor: 'pointer',
            }}>🗑</button>
          )}
        </div>
      </div>

      {/* Webhook URL */}
      <div style={{
        marginTop: 10, padding: '6px 10px', borderRadius: 7,
        background: 'var(--bg-2)', border: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ fontSize: 11, color: 'var(--text-2)', fontWeight: 600 }}>WEBHOOK</span>
        <code style={{ fontSize: 11, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#6366f1' }}>
          POST {webhookUrl}
        </code>
        <button
          onClick={() => navigator.clipboard.writeText(webhookUrl)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--text-2)' }}
          title="Copy webhook URL"
        >📋</button>
      </div>

      {/* Inline result after manual run */}
      {lastResult && (
        <div style={{
          marginTop: 8, padding: '8px 12px', borderRadius: 7,
          background: lastResult.success ? '#f0fdf4' : '#fef2f2',
          border: `1px solid ${lastResult.success ? '#86efac' : '#fca5a5'}`,
          fontSize: 12,
        }}>
          {lastResult.success
            ? <><span style={{ color: '#16a34a', fontWeight: 600 }}>✓ Success</span>{lastResult.output ? ` · ${lastResult.output.substring(0, 100)}` : ''}</>
            : <><span style={{ color: '#dc2626', fontWeight: 600 }}>✗ Error</span>{` · ${lastResult.error ?? 'Unknown error'}`}</>
          }
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SchedulePage
// ---------------------------------------------------------------------------
export default function SchedulePage() {
  const [schedules, setSchedules] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)

  const fetchAll = useCallback(async () => {
    setError('')
    try {
      const res = await listSchedules()
      setSchedules(res.data)
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const handleCreated = (schedule) => {
    setShowForm(false)
    fetchAll()
  }

  return (
    <div style={{ padding: '24px 28px', maxWidth: 900, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0, fontWeight: 700, fontSize: 20 }}>Schedules & Webhooks</h2>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 3 }}>
            Run agents on a cron/interval schedule or trigger via HTTP webhook
          </div>
        </div>
        <button
          onClick={() => setShowForm(v => !v)}
          style={{
            padding: '7px 16px', borderRadius: 8, background: '#6366f1',
            color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 13,
          }}
        >
          {showForm ? '✕ Cancel' : '+ New Schedule'}
        </button>
      </div>

      {error && (
        <div style={{ marginBottom: 16, padding: '10px 14px', borderRadius: 8, background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Create form */}
      {showForm && (
        <CreateForm onCreated={handleCreated} onCancel={() => setShowForm(false)} />
      )}

      {/* Webhook quick-start callout */}
      {!showForm && (
        <div style={{
          marginBottom: 20, padding: '12px 16px', borderRadius: 10,
          background: 'var(--bg-2)', border: '1px solid var(--border)', fontSize: 13,
        }}>
          <b>Webhook quick-start:</b> Create a schedule, then copy its webhook URL and call it with{' '}
          <code style={{ background: 'var(--bg-3, #f1f5f9)', padding: '1px 5px', borderRadius: 4, fontSize: 12 }}>
            curl -X POST &lt;url&gt;
          </code>{' '}
          from CI/CD, n8n, Zapier, or any HTTP tool.
        </div>
      )}

      {/* Schedule list */}
      {loading ? (
        <div style={{ color: 'var(--text-2)', fontSize: 13 }}>Loading…</div>
      ) : schedules.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: 48, borderRadius: 12,
          background: 'var(--bg-1)', border: '1px solid var(--border)',
        }}>
          <div style={{ fontSize: 32, marginBottom: 10 }}>🕐</div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>No schedules yet</div>
          <div style={{ fontSize: 13, color: 'var(--text-2)' }}>
            Create a schedule to run your agent automatically at a fixed interval or on a cron pattern.
          </div>
        </div>
      ) : (
        schedules.map(s => (
          <ScheduleCard key={s.id} schedule={s} onRefresh={fetchAll} />
        ))
      )}
    </div>
  )
}
