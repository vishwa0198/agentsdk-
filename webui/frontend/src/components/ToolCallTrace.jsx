import { useState } from 'react'

function ToolCallCard({ call }) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className={`tool-card ${call.isError ? 'error-card' : ''}`}>
      <button className="tool-card-header" onClick={() => setExpanded(e => !e)}>
        <span className="tool-name">{call.name}</span>
        <span className="tool-toggle">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="tool-card-body">
          {/* Arguments */}
          <div>
            <span className="tool-label">Arguments</span>
            <pre className="tool-pre">
              {JSON.stringify(call.arguments, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {call.result !== null ? (
            <div className={call.isError ? 'tool-error' : ''}>
              <span className="tool-label">Result</span>
              <pre className="tool-pre">
                {typeof call.result === 'string'
                  ? call.result
                  : JSON.stringify(call.result, null, 2)}
              </pre>
            </div>
          ) : (
            <span className="tool-running">⏳ Running…</span>
          )}
        </div>
      )}
    </div>
  )
}

export default function ToolCallTrace({ toolCalls }) {
  return (
    <div className="tool-trace">
      <h3 className="trace-title">Tool Calls</h3>
      <div className="tool-list">
        {toolCalls.map((call, i) => (
          <ToolCallCard key={call.id ?? i} call={call} />
        ))}
      </div>
    </div>
  )
}
