// Mock/demo bootstrap for the screenshot build.
//
// Intercepts window.fetch (the whole API surface goes through it — see src/api.js)
// and window.EventSource (the SSE feed) so every view renders populated with
// fictional data and no backend. Loaded only under `vite --mode mock` from
// index.jsx. The headless capture script (scripts/capture-screenshots.mjs)
// navigates each route and screenshots it.
import * as D from './data'

// ---- response dispatch ------------------------------------------------------

// Ordered rules: first match wins. `re` runs against the pathname; groups are
// passed to the handler. Query string is available as `search`.
const RULES = [
  // auth / boot — solo mode so AuthGate passes straight through
  [/^\/auth\/session$/, () => ({ authenticated: true, login_required: false, has_users: false, principal: { username: 'juan', role: 'admin' } })],
  [/^\/auth\/permissions\/schema$/, () => ({ schema: {} })],
  [/^\/config$/, () => ({ brand: null, features: {} })],
  [/^\/settings$/, () => ({ settings: { theme: 'dark', accent: 'indigo' } })],
  [/^\/health$/, () => ({ status: 'ok' })],
  [/^\/ai\/hub\/health$/, () => ({ ok: true, providers: ['anthropic', 'openai', 'ollama'] })],

  // dashboard / fleet
  [/^\/dashboard\/stats$/, () => D.STATS],
  [/^\/devices$/, () => ({ devices: D.DEVICES })],
  [/^\/devices\/available$/, () => ({ devices: D.DEVICES.filter((d) => d.online) })],
  [/^\/fleet\/health$/, () => D.FLEET_HEALTH],
  [/^\/agent\/status$/, () => D.AGENT_STATUS_ALL],
  [/^\/fleet\/metrics\/sparklines$/, () => ({ sparklines: D.sparklines() })],
  [/^\/fleet\/metrics$/, () => ({ tier: 'hot', series: D.metricSeries() })],
  [/^\/fleet\/compare$/, () => ({ devices: D.DEVICES.slice(0, 3), series: D.metricSeries(D.DEVICES.slice(0, 3).map((d) => d.device_id)) })],

  // fleet query
  [/^\/fleet\/query\/fields$/, () => D.QUERY_FIELDS],
  [/^\/fleet\/query\/presets$/, () => D.QUERY_PRESETS],
  [/^\/fleet\/queries$/, () => D.SAVED_QUERIES],
  [/^\/fleet\/query$/, () => ({ matches: D.DEVICES.slice(0, 3), count: 3, expression: '' })],

  // fleet groups + tags
  [/^\/fleet\/groups$/, () => D.FLEET_GROUPS],
  [/^\/fleet\/groups\/[^/]+$/, (m) => D.FLEET_GROUPS.groups[0]],
  [/^\/devices\/[^/]+\/tags$/, () => ({ tags: [] })],

  // node detail
  [/^\/devices\/([^/]+)\/diagnostics$/, (m) => D.diagnostics(m[1])],
  [/^\/devices\/([^/]+)\/properties$/, () => D.PROPERTIES],
  [/^\/devices\/([^/]+)\/stream\/status$/, () => ({ streaming: false, viewers: 0, available: true })],
  [/^\/devices\/([^/]+)\/sessions$/, () => ({ sessions: [] })],
  [/^\/devices\/([^/]+)\/ui-hierarchy$/, () => ({ hierarchy: '<hierarchy/>' })],
  [/^\/devices\/([^/]+)\/agent\/status$/, () => ({ running: true, mode: 'assist' })],
  [/^\/devices\/([^/]+)\/agent\/usage$/, () => ({ usage: { total_cost: 0.42, total_tokens: 18240 } })],
  [/^\/devices\/([^/]+)\/agent\/pending$/, () => ({ pending: [] })],
  [/^\/devices\/([^/]+)\/conversation\/history$/, () => ({ messages: [] })],
  [/^\/devices\/([^/]+)\/metrics\/sparkline$/, (m) => ({ points: D.metricSeries([m[1]])[0].points })],
  [/^\/devices\/([^/]+)\/metrics$/, (m) => ({ tier: 'hot', points: D.metricSeries([m[1]])[0].points })],
  [/^\/agent\/([^/]+)\/status$/, () => ({ running: true, mode: 'assist' })],
  [/^\/agent\/([^/]+)\/commands$/, () => ({ commands: [] })],
  [/^\/devices\/([^/]+)$/, (m) => D.device(m[1])],

  // automations
  [/^\/automations\/step-types$/, () => D.STEP_TYPES],
  [/^\/automations\/node-pack$/, () => ({
    integration: { id: 'devicekit', name: 'DeviceKit', description: 'Device steps from the step-type registry', icon: 'Smartphone', color: '#6366f1', category: 'Devices' },
    nodes: [],
    supported_builtins: [],
  })],
  [/^\/automations\/schedules$/, () => ({ schedules: [] })],
  [/^\/automations\/runs$/, () => D.AUTOMATION_RUNS],
  [/^\/automations\/runs\/([^/]+)\/regression-report$/, () => ({ baselines: [], summary: { pass: 8, fail: 1, review: 2 } })],
  [/^\/automations\/runs\/([^/]+)$/, () => D.RUN_DETAIL],
  [/^\/automations\/([^/]+)\/graph$/, () => ({ derived: false, graph: { version: 1, nodes: [], edges: [], meta: { mcpServers: [] } } })],
  [/^\/automations\/([^/]+)\/baselines$/, () => ({ baselines: [] })],
  [/^\/automations\/([^/]+)$/, (m) => D.AUTOMATIONS.find((a) => a.id === m[1]) || D.AUTOMATIONS[0]],
  [/^\/automations$/, () => ({ automations: D.AUTOMATIONS })],

  // pipeline
  [/^\/pipeline\/builds\/([^/]+)\/failures$/, () => ({ failures: D.BUILDS.builds[1].failures })],
  [/^\/pipeline\/builds\/([^/]+)$/, (m) => D.BUILDS.builds.find((b) => b.id === m[1]) || D.BUILDS.builds[0]],
  [/^\/pipeline\/builds$/, () => D.BUILDS],

  // profiles
  [/^\/profiles\/device\/([^/]+)$/, () => D.PROFILES[0]],
  [/^\/profiles\/([^/]+)$/, (m) => D.PROFILES.find((p) => p.id === m[1]) || D.PROFILES[0]],
  [/^\/profiles$/, () => ({ profiles: D.PROFILES })],

  // enrollment / onboarding / versions / OTA
  [/^\/agent-devices\/pending$/, () => D.PENDING_DEVICES],
  [/^\/agent-device\/versions$/, () => ({ versions: [{ version: '1.4.0', channel: 'stable', devices: 4 }, { version: '1.3.2', channel: 'stable', devices: 2 }] })],
  [/^\/agent-device\/ota\/releases$/, () => ({ releases: [{ id: 'v140', version: '1.4.0', channel: 'stable', yanked: false }] })],
  [/^\/agent-device\/ota\/rollouts$/, () => ({ rollouts: [] })],
  [/^\/agent-device\/primitives$/, () => ({ primitives: [] })],
  [/^\/onboarding$/, () => ({ onboarding: [] })],

  // command history + jobs + notifications
  [/^\/device-commands$/, () => D.COMMANDS],
  [/^\/jobs\/stats$/, () => D.JOB_STATS],
  [/^\/jobs\/schedules$/, () => ({ schedules: [] })],
  [/^\/jobs$/, () => D.JOBS],
  [/^\/notifications\/unread-count$/, () => ({ count: 3 })],
  [/^\/notifications\/channels$/, () => D.NOTIFICATION_CHANNELS],
  [/^\/notifications\/preferences$/, () => ({ preferences: {} })],
  [/^\/notifications\/events$/, () => ({ events: [] })],
  [/^\/notifications$/, () => D.NOTIFICATIONS],

  // extensions
  [/^\/extensions\/contributions$/, () => ({ nav: [{ route: '/ext/webhook-notify', label: 'Webhook Notify', section: 'Extensions', slug: 'webhook-notify' }], routes: [], page_titles: {}, slots: {} })],
  [/^\/extensions\/registry$/, () => D.EXTENSION_REGISTRY],
  [/^\/extensions\/updates$/, () => ({ updates: [] })],
  [/^\/extensions\/manifest-spec$/, () => ({ spec: {} })],
  [/^\/extensions\/sdk-version$/, () => ({ version: '1.0.0' })],
  [/^\/extensions$/, () => D.EXTENSIONS],
  [/^\/agent-plugins$/, () => ({ plugins: [] })],

  // misc
  [/^\/alerts$/, () => ({ alerts: [] })],
  [/^\/activities$/, () => ({ activities: [] })],
  [/^\/queue\/status$/, () => ({ pending: 0, running: 1 })],
  [/^\/metrics\/catalog$/, () => ({ metrics: ['cpu_load', 'battery_pct', 'temperature', 'mem_used_mb'] })],
  [/^\/metrics\/alert-rules$/, () => ({ rules: [
    { id: 'ar1', metric: 'temperature', op: '>', value: 45, enabled: true },
    { id: 'ar2', metric: 'battery_pct', op: '<', value: 15, enabled: true },
  ] })],
  [/^\/metrics\/alert-rules\/ops$/, () => ({ ops: ['>', '<', '>=', '<=', '='] })],
  [/^\/backups$/, () => ({ backups: [] })],
  [/^\/users$/, () => ({ users: [{ id: 'u1', username: 'juan', role: 'admin' }] })],
  [/^\/api-keys$/, () => ({ keys: [] })],
  [/^\/audit$/, () => ({ entries: [] })],
]

// Sensible fallback so an unmapped endpoint never crashes a view.
function fallback(path) {
  if (/s$/.test(path)) return {} // collections resolve their own key via rules; default empty object
  return {}
}

function dispatch(method, path, search) {
  for (const [re, fn] of RULES) {
    const m = path.match(re)
    if (m) return fn(m, search)
  }
  return fallback(path)
}

// ---- fetch patch ------------------------------------------------------------

const realFetch = window.fetch.bind(window)

window.fetch = async (input, init = {}) => {
  const url = typeof input === 'string' ? input : input.url
  let path
  try {
    path = new URL(url, window.location.origin).pathname
  } catch {
    path = url
  }
  // Only intercept API-ish calls; let Vite/static assets through.
  const isApi = /^\/(dashboard|devices|fleet|automations|pipeline|profiles|agent|agent-device|agent-devices|agent-plugins|extensions|notifications|jobs|onboarding|device-commands|metrics|alerts|activities|queue|backups|auth|config|settings|health|ai|users|api-keys|audit|grants|invitations|vault|search)/.test(path)
  if (!isApi) return realFetch(input, init)

  const method = (init.method || 'GET').toUpperCase()
  const search = url.includes('?') ? url.slice(url.indexOf('?') + 1) : ''
  const body = dispatch(method, path, search)
  return new Response(JSON.stringify(body ?? {}), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

// ---- EventSource patch (SSE) ------------------------------------------------

// A no-op EventSource that reports a live connection so the "LIVE" badge shows,
// then stays quiet. Fictional demo — no streaming events needed for stills.
class MockEventSource {
  constructor() {
    this.listeners = {}
    this.readyState = 1
    setTimeout(() => this._emit('connected', { ok: true }), 60)
    // On a Node Control route, stream a short burst of device_state samples so the
    // live-diagnostics gauges (which accumulate history from live updates) fill in.
    const nodeMatch = window.location.pathname.match(/^\/node\/([^/]+)/)
    if (nodeMatch) {
      const id = nodeMatch[1]
      D.liveMetricsBurst(id).forEach((metrics, i) => {
        setTimeout(() => this._emit('device_state', { device_id: id, state: { metrics } }), 90 + i * 9)
      })
    }
  }
  addEventListener(type, cb) {
    ;(this.listeners[type] ||= []).push(cb)
  }
  removeEventListener(type, cb) {
    this.listeners[type] = (this.listeners[type] || []).filter((f) => f !== cb)
  }
  _emit(type, data) {
    const ev = { data: JSON.stringify(data), type }
    for (const cb of this.listeners[type] || []) cb(ev)
    if (type === 'open' && this.onopen) this.onopen(ev)
  }
  close() {
    this.readyState = 2
  }
}
window.EventSource = MockEventSource

// ---- demo handles -----------------------------------------------------------

window.__demo = {
  data: D,
  // Navigate the SPA without a reload (react-router listens to popstate).
  navigate: (path) => {
    window.history.pushState({}, '', path)
    window.dispatchEvent(new PopStateEvent('popstate'))
  },
}

// eslint-disable-next-line no-console
console.log('[devicekit] mock/demo build — fictional fleet, no backend')
