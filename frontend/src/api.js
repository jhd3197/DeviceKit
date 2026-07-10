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
  runAutomation: (id, deviceId, selfHeal = false) =>
    request(`/automations/${id}/run`, {
      method: 'POST',
      body: JSON.stringify({ device_id: deviceId, self_heal: selfHeal }),
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

  // NL Automation (AI-powered)
  generateSteps: (description, deviceId) =>
    request('/automations/generate', {
      method: 'POST',
      body: JSON.stringify({ description, device_id: deviceId }),
    }),
  refineStep: (step, instruction, deviceId) =>
    request('/automations/refine-step', {
      method: 'POST',
      body: JSON.stringify({ step, instruction, device_id: deviceId }),
    }),
  explainAutomation: (id) => request(`/automations/${id}/explain`),
  getUiHierarchy: (deviceId) => request(`/devices/${deviceId}/ui-hierarchy`),

  // Visual Regression Testing
  getBaselines: (automationId) => request(`/automations/${automationId}/baselines`),
  createBaseline: (automationId, data) =>
    request(`/automations/${automationId}/baselines`, {
      method: 'POST', body: JSON.stringify(data),
    }),
  getBaseline: (automationId, baselineId) =>
    request(`/automations/${automationId}/baselines/${baselineId}`),
  getBaselineImageUrl: (automationId, baselineId) =>
    `${API}/automations/${automationId}/baselines/${baselineId}/image`,
  updateBaseline: (automationId, baselineId, data) =>
    request(`/automations/${automationId}/baselines/${baselineId}`, {
      method: 'PUT', body: JSON.stringify(data),
    }),
  deleteBaseline: (automationId, baselineId) =>
    request(`/automations/${automationId}/baselines/${baselineId}`, { method: 'DELETE' }),
  compareBaseline: (automationId, baselineId, data) =>
    request(`/automations/${automationId}/baselines/${baselineId}/compare`, {
      method: 'POST', body: JSON.stringify(data),
    }),
  getRegressionReport: (runId) => request(`/automations/runs/${runId}/regression-report`),

  // Debug Bundles
  generateDebugBundle: (deviceId, trigger = 'manual', context = {}) =>
    request(`/devices/${deviceId}/debug-bundle`, {
      method: 'POST',
      body: JSON.stringify({ trigger, context }),
    }),
  listDebugBundles: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request(`/debug-bundles${q ? `?${q}` : ''}`)
  },
  getDebugBundle: (id) => request(`/debug-bundles/${id}`),
  downloadDebugBundleUrl: (id) => `${API}/debug-bundles/${id}/download`,
  analyzeDebugBundle: (id) =>
    request(`/debug-bundles/${id}/analyze`, { method: 'POST' }),
  shareDebugBundle: (id, expiresHours = 24) =>
    request(`/debug-bundles/${id}/share`, {
      method: 'POST',
      body: JSON.stringify({ expires_hours: expiresHours }),
    }),
  sharedBundleUrl: (token) => `${API}/debug-bundles/share/${token}`,
  deleteDebugBundle: (id) =>
    request(`/debug-bundles/${id}`, { method: 'DELETE' }),

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

  // Fleet Query Language
  fleetQuery: (expression, format = 'json') =>
    request(`/fleet/query?q=${encodeURIComponent(expression)}&format=${format}`),
  fleetQueryValidate: (expression) =>
    request('/fleet/query/validate', { method: 'POST', body: JSON.stringify({ expression }) }),
  getQueryFields: () => request('/fleet/query/fields'),
  getQueryPresets: () => request('/fleet/query/presets'),
  getSavedQueries: () => request('/fleet/queries'),
  getSavedQuery: (id) => request(`/fleet/queries/${id}`),
  createSavedQuery: (data) =>
    request('/fleet/queries', { method: 'POST', body: JSON.stringify(data) }),
  updateSavedQuery: (id, data) =>
    request(`/fleet/queries/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteSavedQuery: (id) =>
    request(`/fleet/queries/${id}`, { method: 'DELETE' }),
  fleetQueryBulkAction: (expression, action, params = {}) =>
    request('/fleet/query/bulk-action', {
      method: 'POST',
      body: JSON.stringify({ expression, action, params }),
    }),

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

  // Streaming
  streamUrl: (id, fps, quality) => {
    const params = new URLSearchParams({ fps: String(fps), quality: String(quality) })
    if (API_KEY) params.set('api_key', API_KEY)
    return `${API}/devices/${id}/stream?${params}`
  },
  getStreamStatus: (id) => request(`/devices/${id}/stream/status`),

  // Session recording (stream)
  startStreamRecording: (id, data) =>
    request(`/devices/${id}/sessions/record`, { method: 'POST', body: JSON.stringify(data || {}) }),
  stopStreamRecording: (id, sessionId) =>
    request(`/devices/${id}/sessions/${sessionId}/stop`, { method: 'POST' }),
  getStreamSessions: (id) => request(`/devices/${id}/sessions`),
  getStreamSession: (id, sessionId) => request(`/devices/${id}/sessions/${sessionId}`),
  getStreamFrameUrl: (id, sessionId, frameIndex) =>
    `${API}/devices/${id}/sessions/${sessionId}/frames/${frameIndex}`,
  recordStreamEvent: (id, sessionId, event) =>
    request(`/devices/${id}/sessions/${sessionId}/events`, {
      method: 'POST', body: JSON.stringify(event),
    }),

  // Extensions (platform + marketplace)
  getContributions: () => request('/extensions/contributions'),
  getSdkVersion: () => request('/extensions/sdk-version'),
  getManifestSpec: () => request('/extensions/manifest-spec'),
  getExtensions: () => request('/extensions'),
  getExtension: (slug) => request(`/extensions/${slug}`),
  getExtensionRegistry: (refresh = false) =>
    request(`/extensions/registry${refresh ? '?refresh=1' : ''}`),
  getExtensionUpdates: (refresh = false) =>
    request(`/extensions/updates${refresh ? '?refresh=1' : ''}`),
  previewExtension: (body) =>
    request('/extensions/preview', { method: 'POST', body: JSON.stringify(body) }),
  installExtension: (body) =>
    request('/extensions/install', { method: 'POST', body: JSON.stringify(body) }),
  installExtensionUpload: (file, force = false) => {
    const form = new FormData()
    form.append('file', file)
    if (force) form.append('force', '1')
    const headers = {}
    if (API_KEY) headers['X-API-Key'] = API_KEY
    return fetch(`${API}/extensions/install-upload`, { method: 'POST', headers, body: form })
      .then((r) => {
        if (!r.ok) return r.json().then((e) => { throw new Error(e.error || 'Upload failed') })
        return r.json()
      })
  },
  uninstallExtension: (slug, purge = false) =>
    request(`/extensions/${slug}${purge ? '?purge=1' : ''}`, { method: 'DELETE' }),
  updateExtension: (slug) =>
    request(`/extensions/${slug}/update`, { method: 'POST' }),
  enableExtension: (slug) =>
    request(`/extensions/${slug}/enable`, { method: 'POST' }),
  disableExtension: (slug) =>
    request(`/extensions/${slug}/disable`, { method: 'POST' }),
  getExtensionConfig: (slug) => request(`/extensions/${slug}/config`),
  updateExtensionConfig: (slug, data) =>
    request(`/extensions/${slug}/config`, { method: 'PUT', body: JSON.stringify(data) }),

  // Jobs & Scheduler (plan 05)
  listJobs: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString()
    return request(`/jobs${qs ? `?${qs}` : ''}`)
  },
  getJob: (id) => request(`/jobs/${id}`),
  getJobStats: () => request('/jobs/stats'),
  retryJob: (id) => request(`/jobs/${id}/retry`, { method: 'POST' }),
  cancelJob: (id) => request(`/jobs/${id}/cancel`, { method: 'POST' }),
  listScheduledJobs: () => request('/jobs/schedules'),
  runScheduledJob: (id) => request(`/jobs/schedules/${id}/run`, { method: 'POST' }),
  setScheduledJobEnabled: (id, enabled) =>
    request(`/jobs/schedules/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),

  // AI Agent (Prompture)
  getConversationHistory: (deviceId) => request(`/devices/${deviceId}/conversation/history`),
  clearConversation: (deviceId) => request(`/devices/${deviceId}/conversation`, { method: 'DELETE' }),
  getAgentUsage: (deviceId) => request(`/devices/${deviceId}/agent/usage`),
  switchAgentModel: (deviceId, modelName) =>
    request(`/devices/${deviceId}/agent/model`, {
      method: 'PATCH',
      body: JSON.stringify({ model_name: modelName }),
    }),

  // Notifications (plan 06)
  getNotifications: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString()
    return request(`/notifications${qs ? `?${qs}` : ''}`)
  },
  getNotification: (id) => request(`/notifications/${id}`),
  getUnreadCount: () => request('/notifications/unread-count'),
  getNotificationEvents: () => request('/notifications/events'),
  markNotificationRead: (id, read = true) =>
    request(`/notifications/${id}/read`, { method: 'PUT', body: JSON.stringify({ read }) }),
  markAllNotificationsRead: () =>
    request('/notifications/read-all', { method: 'PUT' }),
  deleteNotification: (id) => request(`/notifications/${id}`, { method: 'DELETE' }),
  clearNotifications: () => request('/notifications', { method: 'DELETE' }),
  getNotificationChannels: () => request('/notifications/channels'),
  getNotificationChannel: (channel) => request(`/notifications/channels/${channel}`),
  updateNotificationChannel: (channel, data) =>
    request(`/notifications/channels/${channel}`, { method: 'PUT', body: JSON.stringify(data) }),
  testNotificationChannel: (channel) =>
    request(`/notifications/channels/${channel}/test`, { method: 'POST' }),
  getNotificationPreferences: () => request('/notifications/preferences'),
  updateNotificationPreferences: (data) =>
    request('/notifications/preferences', { method: 'PUT', body: JSON.stringify(data) }),
  setNotificationMute: (data) =>
    request('/notifications/preferences/mute', { method: 'PUT', body: JSON.stringify(data) }),

  // Agent Security & Fleet Registry (plan 07)
  getPendingAgents: () => request('/agent-devices/pending'),
  claimAgent: (code, passphrase) =>
    request('/agent-devices/claim', {
      method: 'POST',
      body: JSON.stringify({ code, passphrase }),
    }),
  getDeviceCommands: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString()
    return request(`/device-commands${qs ? `?${qs}` : ''}`)
  },

  // Metrics History (plan 08)
  getMetricsCatalog: () => request('/metrics/catalog'),
  getDeviceMetrics: (id, metric = 'battery_pct', period = '24h') =>
    request(`/devices/${id}/metrics?metric=${encodeURIComponent(metric)}&period=${period}`),
  getDeviceSparkline: (id, metric = 'battery_pct', period = '24h') =>
    request(`/devices/${id}/metrics/sparkline?metric=${encodeURIComponent(metric)}&period=${period}`),
  getFleetMetrics: (metric = 'battery_pct', deviceIds = null, period = '24h') => {
    const params = new URLSearchParams({ metric, period })
    if (deviceIds && deviceIds.length) params.set('devices', deviceIds.join(','))
    return request(`/fleet/metrics?${params}`)
  },
  getFleetSparklines: (metric = 'battery_pct', deviceIds = null, period = '24h') => {
    const params = new URLSearchParams({ metric, period })
    if (deviceIds && deviceIds.length) params.set('devices', deviceIds.join(','))
    return request(`/fleet/metrics/sparklines?${params}`)
  },
  getMetricAlertRules: (deviceId) =>
    request(`/metrics/alert-rules${deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : ''}`),
  getMetricAlertRuleOps: () => request('/metrics/alert-rules/ops'),
  createMetricAlertRule: (data) =>
    request('/metrics/alert-rules', { method: 'POST', body: JSON.stringify(data) }),
  updateMetricAlertRule: (id, data) =>
    request(`/metrics/alert-rules/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteMetricAlertRule: (id) =>
    request(`/metrics/alert-rules/${id}`, { method: 'DELETE' }),
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
  es.addEventListener('stream_viewer', (e) => {
    handlers.onStreamViewer?.(JSON.parse(e.data))
  })
  es.addEventListener('job', (e) => {
    handlers.onJob?.(JSON.parse(e.data))
  })
  es.addEventListener('notification', (e) => {
    handlers.onNotification?.(JSON.parse(e.data))
  })
  es.onerror = () => {
    handlers.onError?.()
  }

  return es
}
