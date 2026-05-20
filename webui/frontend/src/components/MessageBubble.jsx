import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

// Code block renderer — used by ReactMarkdown.
function CodeBlock({ inline, className, children, ...props }) {
  const match = /language-(\w+)/.exec(className || '')
  if (!inline && match) {
    return (
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={match[1]}
        PreTag="div"
        customStyle={{ margin: 0, borderRadius: 6, fontSize: 12.5 }}
        {...props}
      >
        {String(children).replace(/\n$/, '')}
      </SyntaxHighlighter>
    )
  }
  return <code className="inline-code" {...props}>{children}</code>
}

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'

  // Thinking state — show animated dots while agent is working.
  if (message.thinking) {
    return (
      <div className="bubble-row assistant">
        <div className="bubble thinking-bubble">
          <div className="thinking-dots">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
          {message.thought && (
            <p className="thought-preview">
              {message.thought.slice(0, 100)}{message.thought.length > 100 ? '…' : ''}
            </p>
          )}
        </div>
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
            components={{ code: CodeBlock }}
          >
            {message.content}
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
