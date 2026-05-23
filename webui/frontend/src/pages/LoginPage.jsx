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
    <div className="login-page">
      <div className="login-card">
        {/* Brand */}
        <h1 className="login-brand">agentsdk</h1>
        <p className="login-tagline">AI Agent Platform</p>

        {/* Tab switcher */}
        <div className="login-tabs">
          <button
            className={`login-tab${tab === 'signin' ? ' active' : ''}`}
            onClick={() => { setTab('signin'); setError(''); setSuccess('') }}
            type="button"
          >
            Sign in
          </button>
          <button
            className={`login-tab${tab === 'register' ? ' active' : ''}`}
            onClick={() => { setTab('register'); setError(''); setSuccess('') }}
            type="button"
          >
            Register
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column' }}>
          <label className="login-label">Username</label>
          <input
            className="login-input"
            type="text"
            value={username}
            onChange={e => setUsername(e.target.value)}
            autoComplete="username"
            required
            disabled={loading}
          />

          <label className="login-label">Password</label>
          <input
            className="login-input"
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            autoComplete={tab === 'signin' ? 'current-password' : 'new-password'}
            required
            minLength={tab === 'register' ? 8 : undefined}
            disabled={loading}
          />

          {success && <p className="login-success">{success}</p>}
          {error   && <p className="login-error">{error}</p>}

          <button className="login-btn" type="submit" disabled={loading}>
            {loading
              ? <><span className="send-spinner" style={{ width: 14, height: 14 }} /> Processing…</>
              : tab === 'signin' ? 'Sign in' : 'Create account'}
          </button>
        </form>
      </div>
    </div>
  )
}


