export default function TokenCounter({ stats }) {
  const input = stats.input ?? 0
  const output = stats.output ?? 0
  const total = input + output
  const color = total > 90000 ? 'var(--error)' : total > 50000 ? '#f59e0b' : 'var(--success)'

  return (
    <div
      className="token-counter"
      title={`Session total: ${total.toLocaleString()} tokens (Groq free tier: ~90k/day)`}
      style={{ color }}
    >
      <span>{input.toLocaleString()}↑</span>
      <span>{output.toLocaleString()}↓</span>
      <span style={{ color: 'var(--text-2)', fontSize: 11 }}>⁄{total.toLocaleString()}</span>
    </div>
  )
}
