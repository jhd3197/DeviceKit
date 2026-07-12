// Fictional fleet + canned API payloads for the screenshot/demo build.
//
// Every serial, IP, and metric here is made up — this is the mock-data build the
// README screenshots are captured from (see docs/screenshots/CAPTURE.md). None of
// it touches a real device or backend.

// ---- helpers ----------------------------------------------------------------

// Deterministic pseudo-random so repeated captures are pixel-stable (no Math.random).
let _seed = 1337
function rnd() {
  _seed = (_seed * 1103515245 + 12345) & 0x7fffffff
  return _seed / 0x7fffffff
}
function series(n, base, spread) {
  const out = []
  for (let i = 0; i < n; i++) out.push(Math.round(base + (rnd() - 0.5) * spread))
  return out
}
// Epoch seconds N minutes ago — widgets render relative times ("18m ago") from these.
const agoSec = (min) => Math.floor(Date.now() / 1000) - min * 60

// ---- devices ----------------------------------------------------------------

export const DEVICES = [
  {
    device_id: 'SM-A035M-01', name: 'Galaxy A03s · QA', model: 'SM-A035M',
    manufacturer: 'Samsung', android_version: '13', sdk: '33', sdkInt: 33,
    online: true, status: 'idle', battery_level: 92, cpu_percent: 31,
    temperature: 34.1, currentPackageName: 'com.example.shop',
    launcher: 'One UI Home', ip: '10.20.4.11', tags: ['qa', 'staging'],
    metrics: { cpu_percent: 31, battery_level: 92, mem_used_mb: 2760, mem_total_mb: 5540, temperature: 34.1, storage_used_pct: 61 },
  },
  {
    device_id: 'Pixel-7-02', name: 'Pixel 7 · Prod', model: 'Pixel 7',
    manufacturer: 'Google', android_version: '14', sdk: '34', sdkInt: 34,
    online: true, status: 'running', battery_level: 78, cpu_percent: 54,
    temperature: 39.8, currentPackageName: 'com.example.shop',
    launcher: 'Pixel Launcher', ip: '10.20.4.12', tags: ['prod'],
    metrics: { cpu_percent: 54, battery_level: 78, mem_used_mb: 4120, mem_total_mb: 7860, temperature: 39.8, storage_used_pct: 44 },
  },
  {
    device_id: 'OP-9-03', name: 'OnePlus 9 · Perf', model: 'LE2115',
    manufacturer: 'OnePlus', android_version: '12', sdk: '31', sdkInt: 31,
    online: true, status: 'idle', battery_level: 41, cpu_percent: 22,
    temperature: 31.5, currentPackageName: 'com.android.launcher',
    launcher: 'OxygenOS', ip: '10.20.4.13', tags: ['perf', 'staging'],
    metrics: { cpu_percent: 22, battery_level: 41, mem_used_mb: 3980, mem_total_mb: 11800, temperature: 31.5, storage_used_pct: 52 },
  },
  {
    device_id: 'SM-G991-04', name: 'Galaxy S21 · Regression', model: 'SM-G991B',
    manufacturer: 'Samsung', android_version: '13', sdk: '33', sdkInt: 33,
    online: true, status: 'locked', battery_level: 63, cpu_percent: 47,
    temperature: 42.3, currentPackageName: 'com.example.bank',
    launcher: 'One UI Home', ip: '10.20.4.14', tags: ['regression', 'prod'],
    metrics: { cpu_percent: 47, battery_level: 63, mem_used_mb: 5210, mem_total_mb: 7860, temperature: 42.3, storage_used_pct: 73 },
  },
  {
    device_id: 'moto-g82-05', name: 'Moto G82 · Smoke', model: 'XT2225',
    manufacturer: 'Motorola', android_version: '12', sdk: '31', sdkInt: 31,
    online: true, status: 'idle', battery_level: 18, cpu_percent: 12,
    temperature: 29.7, currentPackageName: 'com.android.launcher',
    launcher: 'Moto App Launcher', ip: '10.20.4.15', tags: ['smoke'],
    metrics: { cpu_percent: 12, battery_level: 18, mem_used_mb: 2450, mem_total_mb: 5540, temperature: 29.7, storage_used_pct: 38 },
  },
  {
    device_id: 'SM-A546-06', name: 'Galaxy A54 · QA', model: 'SM-A546E',
    manufacturer: 'Samsung', android_version: '14', sdk: '34', sdkInt: 34,
    online: false, status: 'offline', battery_level: 55, cpu_percent: 0,
    temperature: 0, currentPackageName: null,
    launcher: 'One UI Home', ip: '10.20.4.16', tags: ['qa'],
    metrics: { cpu_percent: 0, battery_level: 55, mem_used_mb: 0, mem_total_mb: 7860, temperature: 0, storage_used_pct: 49 },
  },
]

// Some views (Device Compare) read RAM off the top-level device, others off
// device.metrics — mirror the fields so both render.
for (const d of DEVICES) {
  d.ram_used_mb = d.metrics.mem_used_mb
  d.ram_total_mb = d.metrics.mem_total_mb
}

export const FLEET_HEALTH = {
  avg_cpu: 33,
  avg_battery: 58,
  avg_temperature: 35.2,
  health_distribution: { healthy: 4, warning: 1, critical: 1 },
  total_ram_used_mb: 18520,
  total_ram_total_mb: 46460,
}

export const STATS = {
  total_devices: DEVICES.length,
  online_devices: DEVICES.filter((d) => d.online).length,
  active_alerts: 2,
  running_automations: 1,
  utilization: 100,
  avg_response_ms: 12,
}

export const AGENT_STATUS_ALL = {
  'SM-A035M-01': { status: 'autonomous', running: true, usage: { total_cost: 0.42, total_tokens: 18240 } },
  'OP-9-03': { status: 'executing_command', running: true, usage: { total_cost: 0.21, total_tokens: 9110 } },
  'moto-g82-05': { status: 'autonomous', running: true, usage: { total_cost: 0.0, total_tokens: 4300 } },
  'Pixel-7-02': { status: 'autonomous', running: true, usage: { total_cost: 0.31, total_tokens: 14200 } },
}

export function sparklines(ids = DEVICES.map((d) => d.device_id)) {
  const out = {}
  for (const id of ids) out[id] = series(24, 60, 40).map((v) => Math.max(4, Math.min(100, v)))
  return out
}

// Time-series for the Metrics Monitor + Compare charts — points are {ts, value}
// over the last 24h (see components/ds/MetricChart.jsx).
export function metricSeries(ids = DEVICES.map((d) => d.device_id), base = 60, spread = 40) {
  const now = Math.floor(Date.now() / 1000)
  return ids.map((id) => ({
    device_id: id,
    points: series(48, base, spread).map((v, i) => ({
      ts: now - (48 - i) * 1800,
      value: Math.max(4, Math.min(100, v)),
    })),
  }))
}

// ---- fleet query ------------------------------------------------------------

export const QUERY_FIELDS = {
  fields: {
    battery: 'number', cpu: 'number', temperature: 'number', android_version: 'number',
    manufacturer: 'string', model: 'string', status: 'string', online: 'boolean', tags: 'array',
  },
}
export const QUERY_PRESETS = {
  presets: [
    { name: 'Low battery', expression: "battery < 20", description: 'Devices under 20% charge' },
    { name: 'Offline', expression: "online = false", description: 'Not currently reachable' },
    { name: 'Outdated OS', expression: "android_version < 13", description: 'Below Android 13' },
    { name: 'Running hot', expression: "temperature > 40", description: 'Above 40°C' },
  ],
}
export const SAVED_QUERIES = {
  queries: [
    { id: 'q1', name: 'Staging pool', expression: "tags IN ('staging')" },
    { id: 'q2', name: 'Prod Samsungs', expression: "manufacturer = 'Samsung' AND tags IN ('prod')" },
  ],
}

// ---- automations ------------------------------------------------------------

export const STEP_TYPES = {
  step_types: [
    { type: 'tap', label: 'Tap', category: 'input' },
    { type: 'swipe', label: 'Swipe', category: 'input' },
    { type: 'type_text', label: 'Type text', category: 'input' },
    { type: 'press_key', label: 'Press key', category: 'input' },
    { type: 'open_app', label: 'Open app', category: 'app' },
    { type: 'close_app', label: 'Close app', category: 'app' },
    { type: 'push_file', label: 'Push file', category: 'files' },
    { type: 'pull_file', label: 'Pull file', category: 'files' },
    { type: 'wait', label: 'Wait', category: 'flow' },
    { type: 'assert', label: 'Assert', category: 'flow' },
    { type: 'screenshot', label: 'Screenshot', category: 'capture' },
    { type: 'screenshot_assert', label: 'Screenshot assert', category: 'capture' },
    { type: 'shell', label: 'Shell', category: 'advanced' },
    { type: 'ai_action', label: 'AI action', category: 'ai' },
  ],
}

const steps = (n) => Array.from({ length: n }, (_, i) => ({ type: 'tap', label: `Step ${i + 1}` }))
export const AUTOMATIONS = [
  { id: 'a1', name: 'Login smoke test', description: 'Open app, sign in, verify home screen', steps: steps(7), tags: ['smoke', 'auth'], device_count: 4, updated_at: agoSec(30), status: 'passing', schedule: 'every 30m' },
  { id: 'a2', name: 'Checkout flow', description: 'Add to cart → checkout → confirm order', steps: steps(14), tags: ['e2e'], device_count: 3, updated_at: agoSec(120), status: 'passing', schedule: null },
  { id: 'a3', name: 'Wi-Fi connect (AI)', description: 'Settings → Wi-Fi → connect TestNetwork', steps: steps(6), tags: ['ai', 'settings'], device_count: 2, updated_at: agoSec(360), status: 'needs-review', schedule: 'every 6h' },
  { id: 'a4', name: 'Onboarding walkthrough', description: 'First-launch tutorial, 5 screens', steps: steps(11), tags: ['onboarding'], device_count: 5, updated_at: agoSec(190), status: 'failing', schedule: null },
]

export const AUTOMATION_RUNS = {
  runs: [
    { id: 'r1', automation_id: 'a2', automation_name: 'Checkout flow', device_id: 'Pixel-7-02', status: 'running', progress: 0.57, completed_steps: 8, step: 8, total_steps: 14, started_at: agoSec(2) },
    { id: 'r2', automation_id: 'a4', automation_name: 'Onboarding walkthrough', device_id: 'SM-G991-04', status: 'failed', completed_steps: 3, step: 4, total_steps: 11, error: 'Element not found: #tutorial-next', started_at: agoSec(24), finished_at: agoSec(23) },
    { id: 'r3', automation_id: 'a1', automation_name: 'Login smoke test', device_id: 'SM-A035M-01', status: 'passed', completed_steps: 7, step: 7, total_steps: 7, started_at: agoSec(6), finished_at: agoSec(5) },
  ],
}

// A single rich run for the Run Detail shot — completed steps, a self-healed
// step, and a failed step with an attached debug bundle (covers per-step
// results + self-healing + debug bundles in one screenshot).
export const RUN_DETAIL = {
  id: 'r9', automation_id: 'a4', automation_name: 'Onboarding walkthrough',
  device_id: 'SM-G991-04', status: 'failed', total_steps: 6, completed_steps: 6,
  started_at: agoSec(24), finished_at: agoSec(23), self_heal: true,
  step_results: [
    { label: 'Open app · com.example.shop', step_type: 'open_app', status: 'completed', duration_ms: 820 },
    { label: 'Tap "Get started"', step_type: 'tap', status: 'completed', duration_ms: 240 },
    {
      label: 'Tap "Next"', step_type: 'tap', status: 'completed', duration_ms: 610,
      healed: true,
      heal_reasoning: 'Button moved from center to the bottom bar in v2.3 — re-located by label match.',
      original_step: { type: 'tap', config: { x: 540, y: 1200 } },
      healed_step: { type: 'tap', config: { selector: 'text=Next' } },
    },
    { label: 'Screenshot assert · home screen', step_type: 'screenshot_assert', status: 'completed', duration_ms: 300 },
    { label: 'Type email · qa@example.com', step_type: 'type_text', status: 'completed', duration_ms: 180 },
    {
      label: 'Tap "#tutorial-next"', step_type: 'tap', status: 'failed', duration_ms: 5000,
      error: 'Element not found: #tutorial-next (waited 5000ms)',
      debug_bundle_id: 'db-1042',
    },
  ],
}

// ---- pipeline ---------------------------------------------------------------

const buildTests = (pass, fail) => [
  ...Array.from({ length: pass }, (_, i) => ({ name: `test_flow_${i + 1}`, status: 'pass', device: DEVICES[i % 4].device_id, duration_ms: 400 + i * 55 })),
  ...Array.from({ length: fail }, (_, i) => ({ name: `test_checkout_${i + 1}`, status: 'fail', device: DEVICES[i % 4].device_id, duration_ms: 5000, error: 'AssertionError: expected order-confirmation screen' })),
]
export const BUILDS = {
  builds: [
    { id: 'b1042', number: 1042, title: 'main · Add discount codes', status: 'passed', passed: 128, failed: 0, errors: 0, skipped: 0, success_rate: 100, duration_ms: 214000, created_at: agoSec(58), started_at: agoSec(62), tests: buildTests(8, 0), failures: [] },
    { id: 'b1041', number: 1041, title: 'pr/checkout · Fix cart TOCTOU', status: 'failed', passed: 121, failed: 7, errors: 0, skipped: 0, success_rate: 95, duration_ms: 240000, created_at: agoSec(136), started_at: agoSec(140), tests: buildTests(6, 3), failures: [{ name: 'test_checkout_1', device: 'Pixel-7-02', error: 'AssertionError: expected order-confirmation screen' }] },
    { id: 'b1040', number: 1040, title: 'main · Bump agent to 1.4.0', status: 'passed', passed: 126, failed: 0, errors: 0, skipped: 2, success_rate: 100, duration_ms: 198000, created_at: agoSec(320), started_at: agoSec(324), tests: buildTests(7, 0), failures: [] },
  ],
}

// ---- profiles ---------------------------------------------------------------

export const PROFILES = [
  { id: 'p1', name: 'QA Analyst', device_id: 'SM-A035M-01', niche: 'E-commerce QA', model: 'claude-sonnet-5', provider: 'anthropic', persona: 'Meticulous tester who narrates each step', tokens: 18240, cost: 0.42 },
  { id: 'p2', name: 'Perf Watcher', device_id: 'OP-9-03', niche: 'Performance', model: 'gpt-4o', provider: 'openai', persona: 'Flags jank and slow frames', tokens: 9110, cost: 0.21 },
  { id: 'p3', name: 'Local Llama', device_id: 'moto-g82-05', niche: 'Offline / air-gapped', model: 'llama3.1', provider: 'ollama', persona: 'Offline agent for air-gapped runs', tokens: 4300, cost: 0.0 },
]

// ---- misc collections -------------------------------------------------------

export const FLEET_GROUPS = {
  groups: [
    { id: 'g1', name: 'QA Pool', color: '#6366f1', device_count: 2, tags: ['qa'], device_ids: ['SM-A035M-01', 'SM-A546-06'] },
    { id: 'g2', name: 'Production', color: '#10b981', device_count: 2, tags: ['prod'], device_ids: ['Pixel-7-02', 'SM-G991-04'] },
    { id: 'g3', name: 'Perf Lab', color: '#f59e0b', device_count: 1, tags: ['perf'], device_ids: ['OP-9-03'] },
  ],
}

export const COMMANDS = {
  commands: [
    { id: 'c1', device_id: 'Pixel-7-02', command: 'reboot', status: 'completed', issued_by: 'juan', created_at: agoSec(9), duration_s: 4.2 },
    { id: 'c2', device_id: 'SM-G991-04', command: 'install apk com.example.bank', status: 'completed', issued_by: 'ci-bot', created_at: agoSec(44), duration_s: 12.8 },
    { id: 'c3', device_id: 'OP-9-03', command: 'run automation a1', status: 'running', issued_by: 'juan', created_at: agoSec(1) },
    { id: 'c4', device_id: 'moto-g82-05', command: 'lock', status: 'failed', issued_by: 'juan', created_at: agoSec(80), error: 'device offline' },
  ],
}

export const PENDING_DEVICES = {
  pending: [
    { id: 'pd1', device_id: 'SM-S911-07', model: 'Galaxy S23', ip: '10.20.4.31', code: '4821', discovered_at: '2026-07-12T14:02:00Z' },
    { id: 'pd2', device_id: 'Pixel-8-08', model: 'Pixel 8 Pro', ip: '10.20.4.32', code: '9930', discovered_at: '2026-07-12T14:00:00Z' },
  ],
}

export const JOBS = {
  jobs: [
    { id: 'j1', kind: 'automation.run', status: 'running', owner_type: 'automation', owner_id: 'a1', attempts: 1, max_attempts: 3, progress: 0.6, created_at: agoSec(2) },
    { id: 'j2', kind: 'fleet.bulk_install', status: 'queued', owner_type: 'group', owner_id: 'g2', attempts: 0, max_attempts: 3, created_at: agoSec(1) },
    { id: 'j3', kind: 'baseline.capture', status: 'completed', owner_type: 'automation', owner_id: 'a2', attempts: 1, max_attempts: 3, created_at: agoSec(33) },
    { id: 'j4', kind: 'debug_bundle.build', status: 'failed', owner_type: 'run', owner_id: 'r9', attempts: 3, max_attempts: 3, created_at: agoSec(23) },
  ],
}
export const JOB_STATS = {
  total: 47,
  by_status: { pending: 1, running: 1, succeeded: 42, failed: 3, cancelled: 0 },
  by_kind: { 'automation.run': 31, 'fleet.bulk_install': 6, 'baseline.capture': 7, 'debug_bundle.build': 3 },
}

export const NOTIFICATIONS = {
  notifications: [
    { id: 'n1', severity: 'info', category: 'fleet', event_key: 'device.new', title: 'New device detected', body: 'SM-S911-07 announced itself on the LAN', read: false, created_at: agoSec(3) },
    { id: 'n2', severity: 'critical', category: 'automation', event_key: 'run.failed', title: 'Automation failed', body: 'Onboarding walkthrough · step 4 on Galaxy S21', read: false, created_at: agoSec(23) },
    { id: 'n3', severity: 'warning', category: 'health', event_key: 'battery.low', title: 'Low battery', body: 'Moto G82 · Smoke is at 18%', read: false, created_at: agoSec(46) },
    { id: 'n4', severity: 'info', category: 'pipeline', event_key: 'build.passed', title: 'Build passed', body: '#1042 · main — 128/128 tests', read: true, created_at: agoSec(58) },
  ],
}
export const NOTIFICATION_CHANNELS = {
  channels: [
    { id: 'ch1', type: 'webhook', name: 'Ops webhook', enabled: true },
    { id: 'ch2', type: 'slack', name: '#qa-alerts', enabled: true },
    { id: 'ch3', type: 'email', name: 'qa@example.com', enabled: false },
  ],
}

export const EXTENSIONS = {
  extensions: [
    { slug: 'devicekit-explorer', name: 'File Explorer', version: '1.2.0', enabled: true, description: 'Browse, upload, and download device files', author: 'DeviceKit' },
    { slug: 'webhook-notify', name: 'Webhook Notify', version: '0.4.1', enabled: true, description: 'Route fleet alerts to any webhook', author: 'DeviceKit' },
    { slug: 'slack-bridge', name: 'Slack Bridge', version: '0.2.0', enabled: false, description: 'Post run results into Slack channels', author: 'community' },
  ],
}
export const EXTENSION_REGISTRY = {
  extensions: [
    { slug: 'grafana-export', name: 'Grafana Export', version: '1.0.0', description: 'Push fleet metrics to Grafana', author: 'community', installed: false },
    { slug: 'jira-sync', name: 'Jira Sync', version: '0.9.0', description: 'File a Jira issue from a debug bundle', author: 'community', installed: false },
    { slug: 'testrail', name: 'TestRail Reporter', version: '1.1.0', description: 'Report pipeline results to TestRail', author: 'community', installed: false },
  ],
}

// ---- node detail ------------------------------------------------------------

export function device(id) {
  return DEVICES.find((d) => d.device_id === id) || DEVICES[0]
}

// A short run of live metric samples for the Node Control diagnostics gauges —
// emitted as SSE device_state events so the CPU/RAM/Battery StepCharts fill in
// (they accumulate history from live updates, so a fresh page has a flat line).
export function liveMetricsBurst(id, n = 45) {
  const d = device(id)
  const out = []
  for (let i = 0; i < n; i++) {
    out.push({
      cpu_percent: Math.round(Math.max(6, Math.min(95, d.metrics.cpu_percent + (rnd() - 0.5) * 30))),
      ram_used_mb: Math.round(Math.max(800, d.metrics.mem_used_mb + (rnd() - 0.5) * 600)),
      ram_total_mb: d.metrics.mem_total_mb,
      battery_level: d.metrics.battery_level,
      battery_temperature: +(d.metrics.temperature + (rnd() - 0.5) * 2).toFixed(1),
      is_charging: false,
    })
  }
  return out
}
export function diagnostics(id) {
  const d = device(id)
  return {
    cpu_percent: d.metrics.cpu_percent, battery_level: d.metrics.battery_level,
    temperature: d.metrics.temperature, mem_used_mb: d.metrics.mem_used_mb,
    mem_total_mb: d.metrics.mem_total_mb, uptime_s: 328140, storage_used_pct: d.metrics.storage_used_pct,
    android_version: d.android_version, sdk: d.sdk, model: d.model, manufacturer: d.manufacturer,
  }
}
export const PROPERTIES = {
  properties: {
    'ro.product.model': 'SM-A035M', 'ro.product.manufacturer': 'Samsung',
    'ro.build.version.release': '13', 'ro.build.version.sdk': '33',
    'ro.serialno': 'R9WT10ABCXY', 'ro.product.cpu.abi': 'arm64-v8a',
  },
}
