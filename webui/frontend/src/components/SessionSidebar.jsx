export default function SessionSidebar({ sessions, activeSession, onSelect, onNew, onDelete }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-title">Sessions</span>
        <button className="btn-primary small" onClick={onNew}>+ New</button>
      </div>

      <ul className="session-list">
        {sessions.length === 0 && (
          <li className="session-empty">No sessions yet.<br />Create one above.</li>
        )}

        {sessions.map(s => (
          <li
            key={s.session_id}
            className={`session-item ${activeSession === s.session_id ? 'active' : ''}`}
          >
            <button className="session-btn" onClick={() => onSelect(s.session_id)}>
              <div className="session-name">{s.session_id}</div>
              <div className="session-meta">
                {s.message_count} msg{s.message_count !== 1 ? 's' : ''} &middot;{' '}
                {new Date(s.updated_at).toLocaleDateString()}
              </div>
            </button>

            <button
              className="delete-btn"
              onClick={e => { e.stopPropagation(); onDelete(s.session_id) }}
              title="Delete session"
            >
              🗑
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}
