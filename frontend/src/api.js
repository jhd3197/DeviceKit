const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5050'

async function request(url, options = {}) {
  const res = await fetch(`${API}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
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

  // Pipeline
  getBuilds: () => request('/pipeline/builds'),
  getBuild: (id) => request(`/pipeline/builds/${id}`),
  startBuild: () => request('/pipeline/builds', { method: 'POST' }),
  getBuildFailures: (id) => request(`/pipeline/builds/${id}/failures`),

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
}
