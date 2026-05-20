import { useRef, useEffect, useState } from 'react'
import MessageBubble from './MessageBubble.jsx'

export default function ChatWindow({ messages, isStreaming, onSend, sessionId }) {
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  // Scroll to bottom whenever messages change.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const submit = () => {
    const text = input.trim()
    if (!text || isStreaming) return
    onSend(text)
    setInput('')
    textareaRef.current?.focus()
  }

  return (
    <div className="chat-window">
      {/* Messages list */}
      <div className="messages-container">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <p>Session: <code>{sessionId}</code></p>
            <p style={{ marginTop: 8, color: 'var(--text-2)', fontSize: 13 }}>
              Type a message below to start. Shift+Enter for a new line.
            </p>
          </div>
        )}

        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="input-area">
        <textarea
          ref={textareaRef}
          className="chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          rows={2}
          disabled={isStreaming}
        />
        <button
          className="send-btn"
          onClick={submit}
          disabled={isStreaming || !input.trim()}
          title="Send"
        >
          {isStreaming ? '…' : '↑'}
        </button>
      </div>
    </div>
  )
}
