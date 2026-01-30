const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5050'
const API_KEY = import.meta.env.VITE_API_KEY || localStorage.getItem('devicekit_api_key') || ''

async function request(url, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  if (API_KEY) headers['X-API-Key'] = API_KEY
  const res = await fetch(`${API}${url}`, {
    headers,
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || res.statusText)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // Dashboard
  getStats: () => request('/dashboard/stats'),
  getDevices: () => request('/devices'),

  // Node Detail
  getDevice: (id) => request(`/devices/${id}`),
  getDiagnostics: (id) => request(`/devices/${id}/diagnostics`),
  getProperties: (id) => request(`/devices/${id}/properties`),
  runAdb: (id, cmd) =>
    request(`/devices/${id}/adb`, {
      method: 'POST',
      body: JSON.stringify({ command: cmd }),
    }),
  reboot: (id) => request(`/devices/${id}/reboot`, { method: 'POST' }),
  screenshotUrl: (id) => `${API}/devices/${id}/screenshot`,
  getFiles: (id, path) =>
    request(`/devices/${id}/files${path ? `?path=${encodeURIComponent(path)}` : ''}`),
  searchFiles: (id, query, path) => {
    const params = new URLSearchParams({ query })
    if (path) params.set('path', path)
    return request(`/devices/${id}/files/search?${params}`)
  },
  uploadFile: (id, file, remotePath) => {
    const form = new FormData()
    form.append('file', file)
    const headers = {}
    if (API_KEY) headers['X-API-Key'] = API_KEY
    return fetch(`${API}/devices/${id}/files/upload?path=${encodeURIComponent(remotePath)}`, {
      method: 'POST',
      headers,
      body: form,
    }).then(r => {
      if (!r.ok) throw new Error('Upload failed')
      return r.json()
    })
  },
  downloadFileUrl: (id, path) =>
    `${API}/devices/${id}/files/download?path=${encodeURIComponent(path)}`,

  // Pipeline
  getBuilds: () => request('/pipeline/builds'),
  getBuild: (id) => request(`/pipeline/builds/${id}`),
  startBuild: (data) =>
    request('/pipeline/builds', { method: 'POST', body: JSON.stringify(data || {}) }),
  getBuildFailures: (id) => request(`/pipeline/builds/${id}/failures`),
  updateBuildStatus: (id, status) =>
    request(`/pipeline/builds/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    }),
  getBuildScreenshot: (buildId, testIndex) =>
    `${API}/pipeline/builds/${buildId}/screenshots/${testIndex}`,

  // Device locking
  getAvailableDevices: () => request('/devices/available'),
  lockDevice: (id, owner, timeout) =>
    request(`/devices/${id}/lock`, {
      method: 'POST',
      body: JSON.stringify({ owner, ...(timeout ? { timeout } : {}) }),
    }),
  unlockDevice: (id, owner) =>
    request(`/devices/${id}/unlock`, {
      method: 'POST',
      body: JSON.stringify({ owner }),
    }),

  // Queue
  getQueueStatus: () => request('/queue/status'),

  // Alerts & Activities
  getAlerts: (params) => {
    const q = new URLSearchParams(params).toString()
    return request(`/alerts${q ? `?${q}` : ''}`)
  },
  createAlert: (data) =>
    request('/alerts', { method: 'POST', body: JSON.stringify(data) }),
  dismissAlert: (id) => request(`/alerts/${id}/dismiss`, { method: 'PUT' }),
  getActivities: (params) => {
    const q = new URLSearchParams(params).toString()
    return request(`/activities${q ? `?${q}` : ''}`)
  },

  // Config
  getConfig: () => request('/config'),
  updateConfig: (data) =>
    request('/config', { method: 'PUT', body: JSON.stringify(data) }),

  // Automations
  getStepTypes: () => request('/automations/step-types'),
  getAutomations: () => request('/automations'),
  getAutomation: (id) => request(`/automations/${id}`),
  createAutomation: (data) =>
    request('/automations', { method: 'POST', body: JSON.stringify(data) }),
  updateAutomation: (id, data) =>
    request(`/automations/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteAutomation: (id) =>
    request(`/automations/${id}`, { method: 'DELETE' }),
  runAutomation: (id, deviceId) =>
    request(`/automations/${id}/run`, {
      method: 'POST',
      body: JSON.stringify({ device_id: deviceId }),
    }),
  getAutomationRuns: (params) => {
    const q = new URLSearchParams(params).toString()
    return request(`/automations/runs${q ? `?${q}` : ''}`)
  },
  getAutomationRun: (id) => request(`/automations/runs/${id}`),
  cancelAutomationRun: (id) =>
    request(`/automations/runs/${id}/cancel`, { method: 'POST' }),

  // Recording
  startRecording: (deviceId) =>
    request('/automations/record/start', {
      method: 'POST',
      body: JSON.stringify({ device_id: deviceId }),
    }),
  stopRecording: (sessionId) =>
    request('/automations/record/stop', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    }),
  recordAction: (sessionId, action) =>
    request('/automations/record/action', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, action }),
    }),

  // Schedules
  getSchedules: (automationId) => {
    const q = automationId ? `?automation_id=${automationId}` : ''
    return request(`/automations/schedules${q}`)
  },
  createSchedule: (data) =>
    request('/automations/schedules', { method: 'POST', body: JSON.stringify(data) }),
  updateSchedule: (id, data) =>
    request(`/automations/schedules/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteSchedule: (id) =>
    request(`/automations/schedules/${id}`, { method: 'DELETE' }),

  // Failure screenshots
  getFailureScreenshotUrl: (runId, stepIndex) =>
    `${API}/automations/runs/${runId}/screenshots/${stepIndex}`,

  // Clone / Export / Import
  cloneAutomation: (id, name) =>
    request(`/automations/${id}/clone`, {
      method: 'POST',
      body: JSON.stringify(name ? { name } : {}),
    }),
  exportAutomation: (id) => request(`/automations/${id}/export`),
  importAutomation: (data) =>
    request('/automations/import', { method: 'POST', body: JSON.stringify(data) }),

  // Device interaction
  tap: (id, x, y) =>
    request(`/devices/${id}/tap`, {
      method: 'POST',
      body: JSON.stringify({ x, y }),
    }),
  press: (id, action) =>
    request(`/devices/${id}/press`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),
  swipe: (id, direction) =>
    request(`/devices/${id}/swipe`, {
      method: 'POST',
      body: JSON.stringify({ direction }),
    }),
  swipeCoords: (id, startX, startY, endX, endY, duration = 400) =>
    request(`/devices/${id}/swipe`, {
      method: 'POST',
      body: JSON.stringify({ startX, startY, endX, endY, duration }),
    }),

  // Fleet Management
  getFleetGroups: () => request('/fleet/groups'),
  getFleetGroup: (id) => request(`/fleet/groups/${id}`),
  createFleetGroup: (data) =>
    request('/fleet/groups', { method: 'POST', body: JSON.stringify(data) }),
  updateFleetGroup: (id, data) =>
    request(`/fleet/groups/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteFleetGroup: (id) =>
    request(`/fleet/groups/${id}`, { method: 'DELETE' }),
  addDeviceToGroup: (groupId, deviceId) =>
    request(`/fleet/groups/${groupId}/devices`, {
      method: 'POST',
      body: JSON.stringify({ device_id: deviceId }),
    }),
  removeDeviceFromGroup: (groupId, deviceId) =>
    request(`/fleet/groups/${groupId}/devices/${deviceId}`, { method: 'DELETE' }),
  bulkCommand: (groupId, command) =>
    request(`/fleet/groups/${groupId}/bulk/command`, {
      method: 'POST',
      body: JSON.stringify({ command }),
    }),
  bulkInstall: (groupId) =>
    request(`/fleet/groups/${groupId}/bulk/install`, { method: 'POST' }),
  bulkReboot: (groupId) =>
    request(`/fleet/groups/${groupId}/bulk/reboot`, { method: 'POST' }),
  getDeviceTags: (id) => request(`/devices/${id}/tags`),
  updateDeviceTags: (id, tags) =>
    request(`/devices/${id}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) }),
  getFleetHealth: () => request('/fleet/health'),
  getFleetComparison: (deviceIds) =>
    request(`/fleet/compare?devices=${deviceIds.join(',')}`),
  onboardDevice: (id) => request(`/devices/${id}/onboard`, { method: 'POST' }),

  // Profiles
  getProfiles: () => request('/profiles'),
  getProfile: (id) => request(`/profiles/${id}`),
  getProfileByDevice: (deviceId) => request(`/profiles/device/${deviceId}`),
  createProfile: (data) =>
    request('/profiles', { method: 'POST', body: JSON.stringify(data) }),
  updateProfile: (id, data) =>
    request(`/profiles/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteProfile: (id) =>
    request(`/profiles/${id}`, { method: 'DELETE' }),

  // AI Agent
  getAgentStatusAll: () => request('/agent/status'),
  getAgentStatus: (deviceId) => request(`/agent/${deviceId}/status`),
  startAgent: (deviceId) =>
    request(`/agent/${deviceId}/start`, { method: 'POST' }),
  stopAgent: (deviceId) =>
    request(`/agent/${deviceId}/stop`, { method: 'POST' }),
  sendCommand: (deviceId, command, priority = 'normal') =>
    request(`/agent/${deviceId}/command`, {
      method: 'POST',
      body: JSON.stringify({ command, priority }),
    }),
  getAgentCommands: (deviceId) => request(`/agent/${deviceId}/commands`),
  getAgentLogs: (deviceId) => request(`/agent/${deviceId}/logs`),
}

export function subscribeToEvents(handlers = {}) {
  const url = API_KEY
    ? `${API}/events/stream?api_key=${encodeURIComponent(API_KEY)}`
    : `${API}/events/stream`
  const es = new EventSource(url)

  es.addEventListener('device_state', (e) => {
    handlers.onDeviceState?.(JSON.parse(e.data))
  })
  es.addEventListener('device_connected', (e) => {
    handlers.onDeviceConnected?.(JSON.parse(e.data))
  })
  es.addEventListener('device_disconnected', (e) => {
    handlers.onDeviceDisconnected?.(JSON.parse(e.data))
  })
  es.addEventListener('device_heartbeat', (e) => {
    handlers.onDeviceHeartbeat?.(JSON.parse(e.data))
  })
  es.addEventListener('device_event', (e) => {
    handlers.onDeviceEvent?.(JSON.parse(e.data))
  })
  es.addEventListener('alert', (e) => {
    handlers.onAlert?.(JSON.parse(e.data))
  })
  es.addEventListener('device_new', (e) => {
    handlers.onDeviceNew?.(JSON.parse(e.data))
  })
  es.addEventListener('bulk_action_complete', (e) => {
    handlers.onBulkActionComplete?.(JSON.parse(e.data))
  })
  es.addEventListener('pipeline_test', (e) => {
    handlers.onPipelineTest?.(JSON.parse(e.data))
  })
  es.addEventListener('pipeline_build', (e) => {
    handlers.onPipelineBuild?.(JSON.parse(e.data))
  })
  es.onerror = () => {
    handlers.onError?.()
  }

  return es
}
