import { useState } from 'react'
import { sendChat } from '../lib/api'

const STORAGE_KEY = 'agentsdk_agents'

const DEFAULT_CONFIG = {
  name: '',
  systemPrompt: 'You are a helpful assistant. Use tools when needed.',
  maxIterations: 10,
  maxTokens: 2048,
  toolsEnabled: true,
  verbose: false,
}

function loadAgents() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

function saveAgents(agents) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(agents))
}

export default function AgentConfigPage() {
  const [agents, setAgents] = useState(loadAgents)
  const [selected, setSelected] = useState(null) // index into agents
  const [form, setForm] = useState(DEFAULT_CONFIG)
  const [testOpen, setTestOpen] = useState(false)
  const [testInput, setTestInput] = useState('')
  const [testResult, setTestResult] = useState('')
  const [testLoading, setTestLoading] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')

  const handleNew = () => {
    setSelected(null)
    setForm(DEFAULT_CONFIG)
    setSaveMsg('')
  }

  const handleSelect = (idx) => {
    setSelected(idx)
    setForm({ ...agents[idx] })
    setSaveMsg('')
  }

  const handleDelete = (idx) => {
    const updated = agents.filter((_, i) => i !== idx)
    saveAgents(updated)
    setAgents(updated)
    if (selected === idx) {
      setSelected(null)
      setForm(DEFAULT_CONFIG)
    } else if (selected > idx) {
      setSelected(selected - 1)
    }
  }

  const handleSave = () => {
    if (!form.name.trim()) { setSaveMsg('Agent name is required.'); return }
    const updated = [...agents]
    if (selected === null) {
      updated.push({ ...form })
      setSelected(updated.length - 1)
    } else {
      updated[selected] = { ...form }
    }
    saveAgents(updated)
    setAgents(updated)
    setSaveMsg('Saved!')
    setTimeout(() => setSaveMsg(''), 2000)
  }

  const handleTest = async () => {
    if (!testInput.trim()) return
    setTestLoading(true)
    setTestResult('')
    try {
      const sessionId = `test-${Date.now()}`
      const res = await sendChat(sessionId, testInput, form.name || 'TestAgent')
      setTestResult(res.data.output)
    } catch (err) {
      setTestResult(`Error: ${err.response?.data?.detail || err.message}`)
    } finally {
      setTestLoading(false)
    }
  }

  return (
    <div style={styles.page}>
      {/* Left: agent list */}
      <aside style={styles.sidebar}>
        <div style={styles.sidebarHeader}>
          <span style={styles.sidebarTitle}>Agents</span>
          <button style={styles.newBtn} onClick={handleNew}>+ New</button>
        </div>
        <ul style={styles.list}>
          {agents.length === 0 && (
            <li style={styles.emptyList}>No agents yet.</li>
          )}
          {agents.map((a, idx) => (
            <li
              key={idx}
              style={{ ...styles.listItem, ...(selected === idx ? styles.listItemActive : {}) }}
            >
              <button style={styles.listBtn} onClick={() => handleSelect(idx)}>
                <span style={styles.listName}>{a.name}</span>
                <span style={styles.listPreview}>
                  {a.systemPrompt.slice(0, 60)}{a.systemPrompt.length > 60 ? '…' : ''}
                </span>
              </button>
              <button
                style={styles.deleteBtn}
                onClick={() => handleDelete(idx)}
                title="Delete agent"
              >
                🗑
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {/* Right: editor */}
      <main style={styles.editor}>
        <h2 style={styles.editorTitle}>
          {selected === null ? 'New Agent' : `Edit: ${form.name || '…'}`}
        </h2>

        <div style={styles.field}>
          <label style={styles.label}>Agent name</label>
          <input
            style={styles.input}
            value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            placeholder="e.g. WebAgent"
          />
        </div>

        <div style={styles.field}>
          <label style={styles.label}>System prompt</label>
          <textarea
            style={{ ...styles.input, ...styles.textarea }}
            rows={6}
            value={form.systemPrompt}
            onChange={e => setForm(f => ({ ...f, systemPrompt: e.target.value }))}
          />
        </div>

        <div style={styles.row}>
          <div style={styles.field}>
            <label style={styles.label}>Max iterations (1–50)</label>
            <input
              style={styles.input}
              type="number"
              min={1}
              max={50}
              value={form.maxIterations}
              onChange={e => setForm(f => ({ ...f, maxIterations: Number(e.target.value) }))}
            />
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Max tokens (256–8192)</label>
            <input
              style={styles.input}
              type="number"
              min={256}
              max={8192}
              step={256}
              value={form.maxTokens}
              onChange={e => setForm(f => ({ ...f, maxTokens: Number(e.target.value) }))}
            />
          </div>
        </div>

        <div style={styles.row}>
          <label style={styles.toggleLabel}>
            <span>Tools enabled</span>
            <div
              style={{ ...styles.toggle, ...(form.toolsEnabled ? styles.toggleOn : {}) }}
              onClick={() => setForm(f => ({ ...f, toolsEnabled: !f.toolsEnabled }))}
            >
              <div style={{ ...styles.toggleThumb, ...(form.toolsEnabled ? styles.toggleThumbOn : {}) }} />
            </div>
          </label>
          <label style={styles.toggleLabel}>
            <span>Verbose</span>
            <div
              style={{ ...styles.toggle, ...(form.verbose ? styles.toggleOn : {}) }}
              onClick={() => setForm(f => ({ ...f, verbose: !f.verbose }))}
            >
              <div style={{ ...styles.toggleThumb, ...(form.verbose ? styles.toggleThumbOn : {}) }} />
            </div>
          </label>
        </div>

        <div style={styles.actions}>
          <button style={styles.btnPrimary} onClick={handleSave}>Save</button>
          <button style={styles.btnSecondary} onClick={() => { setTestOpen(true); setTestResult('') }}>
            Test agent
          </button>
          {saveMsg && <span style={saveMsg === 'Saved!' ? styles.successMsg : styles.errorMsg}>{saveMsg}</span>}
        </div>
      </main>

      {/* Test modal */}
      {testOpen && (
        <div style={styles.modalOverlay} onClick={() => setTestOpen(false)}>
          <div style={styles.modal} onClick={e => e.stopPropagation()}>
            <h3 style={styles.modalTitle}>Test: {form.name || 'Agent'}</h3>
            <textarea
              style={{ ...styles.input, ...styles.textarea, marginBottom: 12 }}
              rows={3}
              placeholder="Enter a test message…"
              value={testInput}
              onChange={e => setTestInput(e.target.value)}
            />
            <button
              style={{ ...styles.btnPrimary, ...(testLoading ? { opacity: 0.6 } : {}) }}
              onClick={handleTest}
              disabled={testLoading}
            >
              {testLoading ? 'Running…' : 'Send'}
            </button>
            {testResult && (
              <div style={styles.testResult}>{testResult}</div>
            )}
            <button style={styles.closeBtn} onClick={() => setTestOpen(false)}>✕ Close</button>
          </div>
        </div>
      )}
    </div>
  )
}

const styles = {
  page: { display: 'flex', height: '100%', overflow: 'hidden', background: 'var(--bg-0)' },
  sidebar: {
    width: 280,
    borderRight: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--bg-1)',
    flexShrink: 0,
  },
  sidebarHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '16px 14px 12px',
    borderBottom: '1px solid var(--border)',
  },
  sidebarTitle: { fontWeight: 700, fontSize: 14, color: 'var(--text-0)' },
  newBtn: {
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    padding: '5px 10px',
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
  },
  list: { listStyle: 'none', overflowY: 'auto', flex: 1 },
  emptyList: { padding: '20px 16px', color: 'var(--text-2)', fontSize: 13 },
  listItem: {
    display: 'flex',
    alignItems: 'center',
    borderBottom: '1px solid var(--border)',
    padding: '2px 8px 2px 0',
  },
  listItemActive: { background: 'var(--bg-3)' },
  listBtn: {
    flex: 1,
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    textAlign: 'left',
    padding: '10px 8px 10px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  listName: { fontSize: 13, fontWeight: 600, color: 'var(--text-0)' },
  listPreview: { fontSize: 11, color: 'var(--text-2)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 190 },
  deleteBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: 14,
    padding: '4px 8px',
    color: 'var(--text-2)',
    flexShrink: 0,
  },
  editor: { flex: 1, padding: '28px 32px', overflowY: 'auto' },
  editorTitle: { fontSize: 18, fontWeight: 700, color: 'var(--text-0)', marginBottom: 24 },
  field: { display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 18 },
  label: { fontSize: 12, fontWeight: 600, color: 'var(--text-1)' },
  input: {
    background: 'var(--bg-2)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text-0)',
    fontSize: 14,
    padding: '9px 12px',
    outline: 'none',
    width: '100%',
  },
  textarea: { resize: 'vertical', fontFamily: 'inherit', lineHeight: 1.55 },
  row: { display: 'flex', gap: 20, marginBottom: 18 },
  toggleLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    cursor: 'pointer',
    fontSize: 13,
    color: 'var(--text-0)',
  },
  toggle: {
    width: 40,
    height: 22,
    borderRadius: 11,
    background: 'var(--bg-3)',
    border: '1px solid var(--border)',
    position: 'relative',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
  toggleOn: { background: 'var(--accent)', border: '1px solid var(--accent)' },
  toggleThumb: {
    width: 16,
    height: 16,
    borderRadius: '50%',
    background: 'var(--text-1)',
    position: 'absolute',
    top: 2,
    left: 2,
    transition: 'transform 0.2s, background 0.2s',
  },
  toggleThumbOn: { transform: 'translateX(18px)', background: '#fff' },
  actions: { display: 'flex', gap: 12, alignItems: 'center', marginTop: 8 },
  btnPrimary: {
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    padding: '10px 22px',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
  },
  btnSecondary: {
    background: 'var(--bg-2)',
    color: 'var(--text-0)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    padding: '10px 22px',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
  },
  successMsg: { color: 'var(--success)', fontSize: 12 },
  errorMsg: { color: 'var(--error)', fontSize: 12 },
  modalOverlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.6)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 100,
  },
  modal: {
    background: 'var(--bg-2)',
    border: '1px solid var(--border)',
    borderRadius: 14,
    padding: '28px 28px 24px',
    width: 440,
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
  },
  modalTitle: { fontSize: 16, fontWeight: 700, color: 'var(--text-0)', marginBottom: 16 },
  testResult: {
    marginTop: 16,
    background: 'var(--bg-1)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    padding: '12px 14px',
    fontSize: 13,
    color: 'var(--text-0)',
    whiteSpace: 'pre-wrap',
    maxHeight: 200,
    overflowY: 'auto',
  },
  closeBtn: {
    marginTop: 16,
    background: 'none',
    border: 'none',
    color: 'var(--text-1)',
    cursor: 'pointer',
    fontSize: 13,
    alignSelf: 'flex-end',
  },
}
