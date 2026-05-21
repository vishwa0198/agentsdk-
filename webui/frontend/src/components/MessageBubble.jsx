import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'

// ---------------------------------------------------------------------------
// Hook: stream text word-by-word when animate=true, show instantly otherwise
// ---------------------------------------------------------------------------
function useStreamText(fullText, animate) {
  const [displayed, setDisplayed] = useState(fullText || '')

  useEffect(() => {
    if (!animate || !fullText) {
      setDisplayed(fullText || '')
      return
    }
    const words = fullText.split(' ')
    let i = 0
    setDisplayed('')
    const interval = setInterval(() => {
      if (i < words.length) {
        setDisplayed(prev => prev + (i > 0 ? ' ' : '') + words[i])
        i++
      } else {
        clearInterval(interval)
      }
    }, 30)
    return () => clearInterval(interval)
  }, [fullText, animate])

  return displayed
}

// ---------------------------------------------------------------------------
// Hook: reactively track data-theme attribute on <html>
// ---------------------------------------------------------------------------
function useIsDark() {
  const [isDark, setIsDark] = useState(
    () => document.documentElement.getAttribute('data-theme') === 'dark'
  )
  useEffect(() => {
    const obs = new MutationObserver(() =>
      setIsDark(document.documentElement.getAttribute('data-theme') === 'dark')
    )
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [])
  return isDark
}

// ---------------------------------------------------------------------------
// Code block with copy button and theme-aware syntax highlighting
// ---------------------------------------------------------------------------
function CodeBlock({ language, children }) {
  const [copied, setCopied] = useState(false)
  const isDark = useIsDark()

  const copy = () => {
    navigator.clipboard.writeText(children)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={copy}
        style={{
          position: 'absolute', top: 8, right: 8,
          background: 'var(--bg-3)', border: 'none',
          borderRadius: 4, padding: '2px 8px',
          fontSize: 11, cursor: 'pointer',
          color: 'var(--text-1)', zIndex: 1,
        }}
      >
        {copied ? 'Copied!' : 'Copy'}
      </button>
      <SyntaxHighlighter
        language={language || 'text'}
        style={isDark ? oneDark : oneLight}
        customStyle={{ borderRadius: 8, fontSize: 13, margin: 0 }}
        PreTag="div"
      >
        {children}
      </SyntaxHighlighter>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Typing indicator — animated three dots while agent is working
// ---------------------------------------------------------------------------
function TypingIndicator({ thought }) {
  return (
    <div className="bubble thinking-bubble">
      <div className="typing-indicator">
        <span /><span /><span />
      </div>
      {thought && (
        <p className="thought-preview">
          {thought.slice(0, 100)}{thought.length > 100 ? '…' : ''}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------
export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const displayedText = useStreamText(message.content, message.animate === true)

  // Thinking state — show typing indicator while agent is reasoning.
  if (message.thinking) {
    return (
      <div className="bubble-row assistant">
        <TypingIndicator thought={message.thought} />
      </div>
    )
  }

  return (
    <div className={`bubble-row ${isUser ? 'user' : 'assistant'}`}>
      <div
        className={[
          'bubble',
          isUser ? 'user-bubble' : 'assistant-bubble',
          message.isError ? 'error-bubble' : '',
        ].join(' ').trim()}
      >
        {isUser ? (
          <p style={{ whiteSpace: 'pre-wrap' }}>{message.content}</p>
        ) : (
          <ReactMarkdown
            components={{
              code({ node, className, children }) {
                const match = /language-(\w+)/.exec(className || '')
                return match
                  ? <CodeBlock language={match[1]}>{String(children).replace(/\n$/, '')}</CodeBlock>
                  : <code style={{ background: 'var(--bg-3)', padding: '1px 5px', borderRadius: 3, fontSize: '0.9em' }}>{children}</code>
              }
            }}
          >
            {displayedText}
          </ReactMarkdown>
        )}

        {/* Token badge on assistant messages */}
        {!isUser && message.tokens && (
          <div className="token-badge">
            ↑&thinsp;{message.tokens.input ?? 0} &nbsp;↓&thinsp;{message.tokens.output ?? 0}
          </div>
        )}
      </div>
    </div>
  )
}
