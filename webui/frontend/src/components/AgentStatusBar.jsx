export default function AgentStatusBar({ activeTool }) {
  return (
    <div className="agent-statusbar">
      <div className="statusbar-dot" />
      <span>Agent running</span>
      {activeTool && (
        <>
          <span className="statusbar-sep">·</span>
          <span className="statusbar-tool">{activeTool}</span>
        </>
      )}
      <div className="statusbar-spacer" />
      <span className="statusbar-hint">Ctrl+K for commands</span>
    </div>
  )
}
