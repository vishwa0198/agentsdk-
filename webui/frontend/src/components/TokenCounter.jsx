export default function TokenCounter({ stats }) {
  const input = stats.input ?? 0
  const output = stats.output ?? 0
  const total = input + output
  const color = total > 90000 ? 'var(--error)' : total > 50000 ? '#f59e0b' : 'var(--text-2)'

  return (
    <div
      className="token-counter"
      title={`Session total: ${total.toLocaleString()} tokens (Groq free tier: ~90k/day)`}
      style={{ color, gap: 6 }}
    >
      <span style={{ color: 'var(--success)', fontWeight: 500 }}>{input.toLocaleString()}↑</span>
      <span style={{ color: 'var(--accent)',  fontWeight: 500 }}>{output.toLocaleString()}↓</span>
      {total > 0 && <span style={{ color, fontSize: 10, opacity: 0.7 }}>{total >= 1000 ? `${(total/1000).toFixed(1)}k` : total}</span>}
    </div>
  )
}
