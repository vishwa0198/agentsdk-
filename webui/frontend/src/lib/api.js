import axios from 'axios'

const api = axios.create({ baseURL: 'http://localhost:8000' })

// Attach token to every request
api.interceptors.request.use(config => {
  const token = localStorage.getItem('agentsdk_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// On 401 → clear token and redirect to /login
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('agentsdk_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------

export const login = (username, password) =>
  api.post(
    '/auth/login',
    new URLSearchParams({ username, password }),
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
  )

export const register = (username, password) =>
  api.post('/auth/register', { username, password })

export const getMe = () => api.get('/auth/me')

// ---------------------------------------------------------------------------
// Session helpers
// ---------------------------------------------------------------------------

export const getSessions = (agentName) => api.get(`/sessions/${agentName}`)

export const deleteSession = (sessionId) => api.delete(`/sessions/${sessionId}`)

// ---------------------------------------------------------------------------
// Chat helpers
// ---------------------------------------------------------------------------

export const sendChat = (sessionId, message, agentName = 'WebAgent') =>
  api.post('/chat', { session_id: sessionId, message, agent_name: agentName })

export const createWebSocket = (sessionId) => {
  const token = localStorage.getItem('agentsdk_token')
  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${wsProto}//localhost:8000/ws/${sessionId}?token=${token}`)
}

// ---------------------------------------------------------------------------
// Memory helpers
// ---------------------------------------------------------------------------

export const getMemories = (sessionId) =>
  api.get(`/memory/${sessionId}`)

export const searchMemory = (sessionId, query, n = 5) =>
  api.get(`/memory/${sessionId}/search`, { params: { q: query, n } })

export const deleteMemory = (sessionId, memoryId) =>
  api.delete(`/memory/${sessionId}/${memoryId}`)

export const clearMemory = (sessionId) =>
  api.delete(`/memory/${sessionId}`)

export const getMemoryStats = (sessionId) =>
  api.get(`/memory/${sessionId}/stats`)
