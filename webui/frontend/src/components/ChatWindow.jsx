import { useRef, useEffect, useState } from 'react'
import MessageBubble from './MessageBubble.jsx'
import { uploadFile } from '../lib/api.js'

// File type → emoji badge
const FILE_ICON = { pdf: '📄', csv: '📊', image: '🖼️', text: '📝', error: '⚠️' }

export default function ChatWindow({ messages, isStreaming, onSend, sessionId }) {
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState([])   // [{file_id, filename, type, text, mime, size}]
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

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
    if ((!text && attachments.length === 0) || isStreaming) return
    // Pass attachments as file context alongside the message
    onSend(text || '(see attached file)', attachments)
    setInput('')
    setAttachments([])
    textareaRef.current?.focus()
  }

  const handleFileChange = async (e) => {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    setUploadError('')
    setUploading(true)
    try {
      const results = await Promise.all(files.map(f => uploadFile(f).then(r => r.data)))
      setAttachments(prev => [...prev, ...results])
    } catch (err) {
      setUploadError(err.response?.data?.detail ?? err.message)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const removeAttachment = (fileId) => {
    setAttachments(prev => prev.filter(a => a.file_id !== fileId))
  }

  return (
    <div className="chat-window">
      {/* Messages list */}
      <div className="messages-container">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <div className="welcome-orb">⚡</div>
            <h2 className="welcome-title">agentsdk</h2>
            <p className="welcome-sub">Ask anything, attach files, and let your agent reason over them.</p>
            <code className="welcome-session">{sessionId}</code>
            <div className="welcome-hints">
              <span className="welcome-hint-chip">📎 Attach PDF / CSV / Image</span>
              <span className="welcome-hint-chip">⌘K Command palette</span>
              <span className="welcome-hint-chip">⇧⏎ New line</span>
            </div>
          </div>
        )}

        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Attachment chips */}
      {attachments.length > 0 && (
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: 6, padding: '6px 12px',
          borderTop: '1px solid var(--border)', background: 'var(--bg-2)',
        }}>
          {attachments.map(a => (
            <div key={a.file_id} style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '3px 8px', borderRadius: 8,
              background: 'var(--bg-1)', border: '1px solid var(--border)',
              fontSize: 12, maxWidth: 200,
            }}>
              <span>{FILE_ICON[a.type] || '📎'}</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {a.filename}
              </span>
              <button
                onClick={() => removeAttachment(a.file_id)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--text-2)', fontSize: 14, lineHeight: 1 }}
              >✕</button>
            </div>
          ))}
        </div>
      )}

      {/* Upload error */}
      {uploadError && (
        <div style={{ padding: '4px 12px', fontSize: 12, color: '#ef4444', background: '#fef2f2' }}>
          {uploadError}
        </div>
      )}

      {/* Input bar */}
      <div className="input-area">
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.csv,.txt,.md,.json,.py,.js,.ts,.png,.jpg,.jpeg,.gif,.webp,.yaml,.yml,.toml,.xml,.html,.css,.sh,.sql"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
        <div className="input-wrapper">
          <button
            className="input-attach"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || isStreaming}
            title="Attach file (PDF, CSV, image, text)"
          >
            {uploading ? <span className="send-spinner" style={{ width: 12, height: 12, borderWidth: 1.5 }} /> : '📎'}
          </button>
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
        </div>
        <button
          className="send-btn"
          onClick={submit}
          disabled={isStreaming || (!input.trim() && attachments.length === 0)}
          title="Send"
        >
          {isStreaming ? <span className="send-spinner" /> : '↑'}
        </button>
      </div>
    </div>
  )
}
