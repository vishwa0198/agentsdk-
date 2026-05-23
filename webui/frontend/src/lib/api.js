import axios from 'axios'

// In Docker/production nginx proxies API calls, so the base URL is relative.
// Set VITE_API_URL to override (e.g. for a standalone backend URL in dev).
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? '' })

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
  // Use the current host so the connection routes through nginx in Docker.
  // In dev, Vite proxies /ws to localhost:8000 automatically.
  const wsBase = import.meta.env.VITE_WS_URL ?? `${wsProto}//${window.location.host}`
  return new WebSocket(`${wsBase}/ws/${sessionId}?token=${token}`)
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

// ---------------------------------------------------------------------------
// MCP helpers
// ---------------------------------------------------------------------------

export const getMCPServers = () =>
  api.get('/mcp/servers')

export const addMCPServer = (body) =>
  api.post('/mcp/servers', body)

export const removeMCPServer = (serverId) =>
  api.delete(`/mcp/servers/${serverId}`)

export const connectMCPServer = (serverId) =>
  api.post(`/mcp/servers/${serverId}/connect`)

export const disconnectMCPServer = (serverId) =>
  api.post(`/mcp/servers/${serverId}/disconnect`)

// ---------------------------------------------------------------------------
// Pipeline helpers
// ---------------------------------------------------------------------------

export const listPipelines = () =>
  api.get('/pipelines')

export const getPipeline = (id) =>
  api.get(`/pipelines/${id}`)

export const savePipeline = (config) =>
  api.post('/pipelines', config)

export const deletePipeline = (id) =>
  api.delete(`/pipelines/${id}`)

export const runPipelineAdhoc = (pipeline, input) =>
  api.post('/pipelines/run', { pipeline, input })

export const runSavedPipeline = (id, input) =>
  api.post(`/pipelines/${id}/run`, { input })

// ---------------------------------------------------------------------------
// Monitor helpers
// ---------------------------------------------------------------------------

export const getMonitorStats = () =>
  api.get('/monitor/stats')

export const getMonitorRuns = (limit = 50, agent = null) =>
  api.get('/monitor/runs', { params: { limit, ...(agent ? { agent } : {}) } })

export const getMonitorRunDetail = (runId) =>
  api.get(`/monitor/runs/${runId}`)

// ---------------------------------------------------------------------------
// File upload helpers
// ---------------------------------------------------------------------------

export const uploadFile = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } })
}

export const ingestMemoryFile = (sessionId, file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/memory/${sessionId}/ingest`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// ---------------------------------------------------------------------------
// Schedule helpers
// ---------------------------------------------------------------------------

export const listSchedules = () =>
  api.get('/schedules')

export const createSchedule = (body) =>
  api.post('/schedules', body)

export const getSchedule = (id) =>
  api.get(`/schedules/${id}`)

export const deleteSchedule = (id) =>
  api.delete(`/schedules/${id}`)

export const enableSchedule = (id) =>
  api.post(`/schedules/${id}/enable`)

export const disableSchedule = (id) =>
  api.post(`/schedules/${id}/disable`)

export const runScheduleNow = (id) =>
  api.post(`/schedules/${id}/run`)
