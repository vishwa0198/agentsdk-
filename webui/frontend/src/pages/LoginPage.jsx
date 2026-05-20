import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, register } from '../lib/api'

export default function LoginPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('signin') // 'signin' | 'register'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      if (tab === 'signin') {
        const res = await login(username, password)
        localStorage.setItem('agentsdk_token', res.data.access_token)
        navigate('/')
      } else {
        await register(username, password)
        setSuccess('Account created! You can now sign in.')
        setTab('signin')
        setPassword('')
      }
    } catch (err) {
      const detail = err.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        {/* App name */}
        <h1 style={styles.appName}>agentsdk</h1>
        <p style={styles.tagline}>AI Agent Platform</p>

        {/* Tab switcher */}
        <div style={styles.tabs}>
          <button
            style={{ ...styles.tab, ...(tab === 'signin' ? styles.tabActive : {}) }}
            onClick={() => { setTab('signin'); setError(''); setSuccess('') }}
            type="button"
          >
            Sign in
          </button>
          <button
            style={{ ...styles.tab, ...(tab === 'register' ? styles.tabActive : {}) }}
            onClick={() => { setTab('register'); setError(''); setSuccess('') }}
            type="button"
          >
            Register
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={styles.form}>
          <label style={styles.label}>Username</label>
          <input
            style={styles.input}
            type="text"
            value={username}
            onChange={e => setUsername(e.target.value)}
            autoComplete="username"
            required
            disabled={loading}
          />

          <label style={styles.label}>Password</label>
          <input
            style={styles.input}
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            autoComplete={tab === 'signin' ? 'current-password' : 'new-password'}
            required
            minLength={tab === 'register' ? 8 : undefined}
            disabled={loading}
          />

          {success && <p style={styles.success}>{success}</p>}
          {error && <p style={styles.error}>{error}</p>}

          <button style={{ ...styles.btn, ...(loading ? styles.btnDisabled : {}) }} type="submit" disabled={loading}>
            {loading
              ? <span style={styles.spinner} />
              : tab === 'signin' ? 'Sign in' : 'Create account'}
          </button>
        </form>
      </div>
    </div>
  )
}

const styles = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--bg-0)',
  },
  card: {
    width: 360,
    background: 'var(--bg-2)',
    border: '1px solid var(--border)',
    borderRadius: 16,
    padding: '36px 32px 32px',
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
  },
  appName: {
    fontSize: 28,
    fontWeight: 700,
    color: 'var(--accent)',
    textAlign: 'center',
    letterSpacing: '-0.5px',
    marginBottom: 4,
  },
  tagline: {
    color: 'var(--text-1)',
    fontSize: 13,
    textAlign: 'center',
    marginBottom: 24,
  },
  tabs: {
    display: 'flex',
    borderRadius: 8,
    background: 'var(--bg-1)',
    padding: 3,
    marginBottom: 24,
    gap: 3,
  },
  tab: {
    flex: 1,
    padding: '7px 0',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    background: 'transparent',
    color: 'var(--text-1)',
    transition: 'all 0.15s',
  },
  tabActive: {
    background: 'var(--bg-3)',
    color: 'var(--text-0)',
    boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  label: {
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--text-1)',
    marginTop: 8,
    marginBottom: 2,
  },
  input: {
    background: 'var(--bg-1)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text-0)',
    fontSize: 14,
    padding: '10px 12px',
    outline: 'none',
    width: '100%',
  },
  btn: {
    marginTop: 16,
    padding: '11px 0',
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 42,
  },
  btnDisabled: {
    opacity: 0.6,
    cursor: 'not-allowed',
  },
  spinner: {
    width: 16,
    height: 16,
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: '#fff',
    borderRadius: '50%',
    animation: 'spin 0.7s linear infinite',
    display: 'inline-block',
  },
  error: {
    color: 'var(--error)',
    fontSize: 12,
    marginTop: 4,
  },
  success: {
    color: 'var(--success)',
    fontSize: 12,
    marginTop: 4,
  },
}
