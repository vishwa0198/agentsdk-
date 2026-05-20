export default function TokenCounter({ stats }) {
  return (
    <div className="token-counter" title="Cumulative tokens for this UI session">
      <span>↑ {stats.input.toLocaleString()}</span>
      <span>↓ {stats.output.toLocaleString()}</span>
    </div>
  )
}
