import { useState } from 'react'

const ROLE_LABELS = { human: 'Human', ai: 'AI', system: 'System', tool_result: 'Tool Result' }

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

export default function MemoryModal({ memory, onClose }) {
  const [copied, setCopied] = useState(false)

  if (!memory) return null

  const copy = () => {
    navigator.clipboard.writeText(memory.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    // In-flow overlay — no position:fixed
    <div
      style={{
        minHeight: '100vh',
        background: 'rgba(0,0,0,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        position: 'absolute',
        inset: 0,
        zIndex: 200,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        style={{
          background: 'var(--bg-1)',
          borderRadius: 12,
          width: '100%',
          maxWidth: 560,
          boxShadow: '0 20px 60px rgba(0,0,0,0.35)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          borderBottom: '1px solid var(--border)',
        }}>
          <span style={{ fontWeight: 600, fontSize: 15 }}>Memory Detail</span>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 18, color: 'var(--text-2)', lineHeight: 1, padding: '2px 6px',
            }}
            aria-label="Close"
          >✕</button>
        </div>

        {/* Meta */}
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', flexWrap: 'wrap', gap: '10px 24px' }}>
          <MetaItem label="Role" value={ROLE_LABELS[memory.role] ?? memory.role} />
          <MetaItem label="Created" value={fmtDate(memory.created_at)} />
          <MetaItem label="Characters" value={memory.content.length.toLocaleString()} />
        </div>

        {/* Content */}
        <div style={{ padding: '14px 20px' }}>
          <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--text-2)', marginBottom: 8 }}>
            Content
          </div>
          <div
            style={{
              maxHeight: 400,
              overflowY: 'auto',
              background: 'var(--bg-2)',
              borderRadius: 8,
              padding: '12px 14px',
              fontSize: 13,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              color: 'var(--text-0)',
              border: '1px solid var(--border)',
            }}
          >
            {memory.content}
          </div>
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 8,
          padding: '12px 20px', borderTop: '1px solid var(--border)',
        }}>
          <button
            onClick={copy}
            style={{
              padding: '6px 16px', borderRadius: 6, fontSize: 13,
              background: 'var(--bg-3)', border: '1px solid var(--border)',
              cursor: 'pointer', color: 'var(--text-1)',
            }}
          >
            {copied ? 'Copied!' : 'Copy'}
          </button>
          <button
            onClick={onClose}
            style={{
              padding: '6px 16px', borderRadius: 6, fontSize: 13,
              background: 'var(--accent)', border: 'none',
              cursor: 'pointer', color: '#fff', fontWeight: 500,
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

function MetaItem({ label, value }) {
  return (
    <div>
      <span style={{ fontSize: 11, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: 0.4, display: 'block' }}>{label}</span>
      <span style={{ fontSize: 13, color: 'var(--text-0)' }}>{value}</span>
    </div>
  )
}
