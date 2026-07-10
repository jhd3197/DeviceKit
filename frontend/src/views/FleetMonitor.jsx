import React, { useEffect, useMemo, useState, useCallback } from 'react'
import { ChevronRight, RefreshCw, Bell, Plus, Trash2, AlertTriangle } from 'lucide-react'
import { api } from '../api'
import MetricChart, { seriesColor } from '../components/ds/MetricChart'

// Friendly labels / units / fixed domains for the queryable metric columns (plan 08).
export const METRIC_META = {
  battery_pct: { label: 'Battery', unit: '%', yMin: 0, yMax: 100 },
  cpu_load: { label: 'CPU Load', unit: '%', yMin: 0, yMax: 100 },
  battery_temp: { label: 'Battery Temp', unit: '°C' },
  mem_free: { label: 'Memory Free', unit: ' MB' },
  storage_free: { label: 'Storage Free', unit: ' MB' },
}

const PERIODS = ['1h', '6h', '24h', '7d', '30d']

export default function FleetMonitor() {
  const [metrics, setMetrics] = useState(Object.keys(METRIC_META))
  const [metric, setMetric] = useState('battery_pct')
  const [period, setPeriod] = useState('24h')
  const [devices, setDevices] = useState([])
  const [selected, setSelected] = useState([])
  const [series, setSeries] = useState([])
  const [tier, setTier] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.getMetricsCatalog().then((r) => {
      if (r.metrics?.length) setMetrics(r.metrics)
    }).catch(() => {})
    api.getDevices().then((r) => {
      const list = r.devices || []
      setDevices(list)
      setSelected(list.slice(0, 6).map((d) => d.device_id))
    }).catch(() => {})
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.getFleetMetrics(metric, selected.length ? selected : null, period)
      setTier(res.tier || '')
      const labelFor = (id) =>
        devices.find((d) => d.device_id === id)?.model || id
      setSeries((res.series || []).map((s, i) => ({
        id: s.device_id,
        label: labelFor(s.device_id),
        color: seriesColor(i),
        points: s.points || [],
      })))
    } catch {
      setSeries([])
    } finally {
      setLoading(false)
    }
  }, [metric, period, selected, devices])

  useEffect(() => { load() }, [load])

  const meta = METRIC_META[metric] || { label: metric, unit: '' }
  const fmt = useMemo(() => {
    if (meta.unit === ' MB') return (v) => `${(v / 1024).toFixed(1)}G`
    return (v) => `${Math.round(v)}${meta.unit || ''}`
  }, [meta])

  const toggleDevice = (id) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  return (
    <>
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-black/50 backdrop-blur-md shrink-0">
        <div className="flex items-center gap-2 text-xs font-medium text-zinc-500">
          <span>Fleet</span>
          <ChevronRight className="w-3 h-3" />
          <span className="text-zinc-200">Metrics Monitor</span>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-xs text-zinc-400 hover:text-white border border-main px-3 py-1.5 rounded transition-colors"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-8 space-y-6 max-w-7xl">
        {/* Metric + period selectors */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-1.5 flex-wrap">
            {metrics.map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                  metric === m
                    ? 'bg-zinc-800 border-zinc-600 text-white'
                    : 'border-main text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {METRIC_META[m]?.label || m}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1 ml-auto">
            {PERIODS.map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`text-[11px] px-2.5 py-1 rounded border transition-colors mono ${
                  period === p
                    ? 'bg-emerald-950 border-emerald-800 text-emerald-400'
                    : 'border-main text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Chart */}
        <div className="bg-card border border-main rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">
              {meta.label} <span className="text-zinc-600 font-normal">· {period}</span>
            </h3>
            {tier && (
              <span className="text-[10px] mono text-zinc-600 uppercase">
                {tier} tier · {series.reduce((a, s) => a + s.points.length, 0)} pts
              </span>
            )}
          </div>
          <MetricChart
            series={series}
            unit={meta.unit}
            yMin={meta.yMin}
            yMax={meta.yMax}
            valueFormat={fmt}
            height={280}
          />
          {/* Legend */}
          <div className="flex flex-wrap gap-3">
            {series.map((s) => (
              <span key={s.id} className="flex items-center gap-1.5 text-[11px] text-zinc-400">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: s.color }} />
                {s.label}
              </span>
            ))}
          </div>
        </div>

        {/* Device selection */}
        <div className="bg-card border border-main rounded-xl p-5">
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-3">
            Devices ({selected.length}/{devices.length})
          </p>
          <div className="flex flex-wrap gap-2">
            {devices.map((d) => (
              <button
                key={d.device_id}
                onClick={() => toggleDevice(d.device_id)}
                className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                  selected.includes(d.device_id)
                    ? 'bg-zinc-800 border-zinc-600 text-white'
                    : 'border-main text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {d.model || d.device_id}
              </button>
            ))}
            {devices.length === 0 && (
              <span className="text-xs text-zinc-600">No devices connected.</span>
            )}
          </div>
        </div>

        {/* Threshold alert rules */}
        <AlertRulesPanel metrics={metrics} />
      </div>
    </>
  )
}

function AlertRulesPanel({ metrics }) {
  const [rules, setRules] = useState([])
  const [ops, setOps] = useState(['<', '<=', '>', '>=', '=', '!='])
  const [form, setForm] = useState({
    metric: 'battery_pct', op: '<', value: 20, event_key: 'device.battery.low',
  })
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    api.getMetricAlertRules().then((r) => setRules(r.rules || [])).catch(() => {})
  }, [])

  useEffect(() => {
    load()
    api.getMetricAlertRuleOps().then((r) => r.ops && setOps(r.ops)).catch(() => {})
  }, [load])

  const create = async () => {
    setError(null)
    try {
      await api.createMetricAlertRule({
        metric: form.metric,
        op: form.op,
        value: Number(form.value),
        event_key: form.event_key || 'device.metric.threshold',
      })
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  const remove = async (id) => {
    try { await api.deleteMetricAlertRule(id); load() } catch {}
  }

  const toggle = async (rule) => {
    try { await api.updateMetricAlertRule(rule.id, { enabled: !rule.enabled }); load() } catch {}
  }

  return (
    <div className="bg-card border border-main rounded-xl p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Bell className="w-4 h-4 text-amber-500" />
        <h3 className="text-sm font-semibold">Threshold Alert Rules</h3>
        <span className="text-[10px] text-zinc-600">
          Evaluated on every heartbeat → notification bus
        </span>
      </div>

      {/* Add rule */}
      <div className="flex flex-wrap items-end gap-2">
        <select
          value={form.metric}
          onChange={(e) => setForm({ ...form, metric: e.target.value })}
          className="bg-black border border-main px-2 py-1.5 text-xs rounded focus:outline-none"
        >
          {metrics.map((m) => <option key={m} value={m}>{METRIC_META[m]?.label || m}</option>)}
        </select>
        <select
          value={form.op}
          onChange={(e) => setForm({ ...form, op: e.target.value })}
          className="bg-black border border-main px-2 py-1.5 text-xs rounded focus:outline-none mono"
        >
          {ops.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        <input
          type="number"
          value={form.value}
          onChange={(e) => setForm({ ...form, value: e.target.value })}
          className="bg-black border border-main px-2 py-1.5 text-xs rounded focus:outline-none w-24 mono"
          placeholder="value"
        />
        <input
          value={form.event_key}
          onChange={(e) => setForm({ ...form, event_key: e.target.value })}
          className="bg-black border border-main px-2 py-1.5 text-xs rounded focus:outline-none w-56 mono"
          placeholder="event key (e.g. device.battery.low)"
        />
        <button
          onClick={create}
          className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-3 py-1.5 rounded transition-colors"
        >
          <Plus className="w-3 h-3" /> Add Rule
        </button>
      </div>
      {error && (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <AlertTriangle className="w-3 h-3" /> {error}
        </div>
      )}

      {/* Rules list */}
      <div className="space-y-1.5">
        {rules.length === 0 && (
          <p className="text-xs text-zinc-600">No rules yet.</p>
        )}
        {rules.map((r) => (
          <div
            key={r.id}
            className="flex items-center gap-3 bg-black/40 border border-main rounded px-3 py-2 text-xs"
          >
            <button
              onClick={() => toggle(r)}
              className={`w-2 h-2 rounded-full shrink-0 ${r.enabled ? 'bg-emerald-500' : 'bg-zinc-700'}`}
              title={r.enabled ? 'Enabled — click to disable' : 'Disabled — click to enable'}
            />
            <span className="mono text-zinc-300">
              {METRIC_META[r.metric]?.label || r.metric} {r.op} {r.value}
            </span>
            <ChevronRight className="w-3 h-3 text-zinc-700" />
            <span className="mono text-amber-400">{r.event_key}</span>
            {r.device_id && (
              <span className="text-[10px] text-zinc-500">· {r.device_id}</span>
            )}
            <span className="text-[10px] text-zinc-600 ml-auto">cooldown {r.cooldown_seconds}s</span>
            <button
              onClick={() => remove(r.id)}
              className="text-zinc-600 hover:text-red-400 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
