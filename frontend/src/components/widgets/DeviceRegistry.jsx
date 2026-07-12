import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, LayoutGrid, List, Smartphone } from 'lucide-react'
import Sparkline from '../ds/Sparkline'

const VIEW_KEY = 'devicekit_device_view'

function getStatus(d) {
  if (!d || d.online === false)
    return { label: 'OFFLINE', color: 'text-zinc-500', dot: 'bg-zinc-600' }
  if (d.currentPackageName && d.currentPackageName !== 'com.android.launcher3')
    return { label: 'RUNNING', color: 'text-emerald-500', dot: 'bg-emerald-500' }
  return { label: 'IDLE', color: 'text-zinc-400', dot: 'bg-zinc-500' }
}

function deviceMetrics(d) {
  return {
    cpu: d.cpu_percent ?? d.metrics?.cpu_percent ?? null,
    battery: d.battery_level ?? d.metrics?.battery_level ?? null,
  }
}

function MeterBar({ label, value, dangerWhen, barClass = 'bg-emerald-500' }) {
  const danger = value != null && dangerWhen?.(value)
  return (
    <div className="flex items-center gap-2">
      <span className="text-[9px] text-zinc-600 uppercase w-7">{label}</span>
      <div className="flex-1 bg-zinc-800 h-1 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${danger ? 'bg-red-500' : barClass}`}
          style={{ width: `${value ?? 0}%` }}
        />
      </div>
      <span className="text-[10px] mono w-9 text-right text-zinc-300">
        {value != null ? `${Math.round(value)}%` : '--'}
      </span>
    </div>
  )
}

function DeviceCard({ device, spark, onOpen }) {
  const status = getStatus(device)
  const { cpu, battery } = deviceMetrics(device)
  const offline = status.label === 'OFFLINE'

  return (
    <button
      onClick={onOpen}
      className={`text-left bg-card border border-main rounded-lg p-4 space-y-3 transition-colors hover:border-zinc-600 ${
        offline ? 'opacity-60' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-zinc-100 truncate">
            {device.model || device.name || 'Unknown'}
          </p>
          <p className="text-[10px] mono text-zinc-500 truncate mt-0.5">
            #{device.device_id}
            {(device.sdkInt || device.sdk) && <span className="ml-2">SDK {device.sdkInt || device.sdk}</span>}
          </p>
        </div>
        <span className={`flex items-center gap-1.5 text-[10px] font-medium shrink-0 ${status.color}`}>
          <span className={`w-1.5 h-1.5 ${status.dot} rounded-full`} />
          {status.label}
        </span>
      </div>

      <Sparkline
        values={spark}
        color={battery != null && battery < 20 ? '#ef4444' : '#10b981'}
        width={240}
        height={30}
      />

      <div className="space-y-1.5">
        <MeterBar label="CPU" value={cpu} dangerWhen={(v) => v > 90} />
        <MeterBar label="BAT" value={battery} dangerWhen={(v) => v < 20} barClass="bg-white" />
      </div>
    </button>
  )
}

// The device grid/table — the big one. Shows the live fleet, or the FQL query result set
// when a query is active. Card grid by default with a persisted grid/table switcher; both
// views share the same status/metric derivation. Reads the shared device list, 24h battery
// sparklines, and the current query result via props (plan 11).
export default function DeviceRegistry({ devices = [], sparklines = {}, queryResult }) {
  const navigate = useNavigate()
  const [filter, setFilter] = useState('')
  const [view, setView] = useState(() => localStorage.getItem(VIEW_KEY) || 'grid')

  const setViewPersisted = (v) => {
    setView(v)
    localStorage.setItem(VIEW_KEY, v)
  }

  const queryActive = !!queryResult?.active
  const displayDevices = queryActive && queryResult.matches ? queryResult.matches : devices
  const filtered = displayDevices.filter((d) =>
    (d.device_id || '').toLowerCase().includes(filter.toLowerCase())
  )

  const emptyMessage = devices.length === 0
    ? 'No devices connected. Connect an Android device via USB.'
    : 'No devices match filter.'

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Smartphone className="w-3.5 h-3.5 text-zinc-500" />
          {queryActive ? 'Query Results' : 'Devices'}
          {filtered.length > 0 && (
            <span className="text-[10px] mono text-zinc-500">{filtered.length}</span>
          )}
        </h3>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Filter by ID..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="bg-black border border-main px-3 py-1 text-xs rounded focus:outline-none focus:border-zinc-500 w-48"
          />
          <div className="flex border border-main rounded overflow-hidden">
            <button
              onClick={() => setViewPersisted('grid')}
              title="Grid view"
              className={`p-1.5 transition-colors ${
                view === 'grid' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-200'
              }`}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewPersisted('table')}
              title="Table view"
              className={`p-1.5 transition-colors ${
                view === 'table' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-200'
              }`}
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="bg-card border border-main rounded-lg p-8 text-center text-zinc-600 text-xs">
          {emptyMessage}
        </div>
      ) : view === 'grid' ? (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 2xl:grid-cols-3">
          {filtered.map((d) => (
            <DeviceCard
              key={d.device_id}
              device={d}
              spark={sparklines[d.device_id] || []}
              onOpen={() => navigate(`/node/${d.device_id}`)}
            />
          ))}
        </div>
      ) : (
        <div className="bg-card border border-main rounded-lg overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest bg-zinc-900/20">
              <tr>
                <th className="p-4 border-b border-main">Device ID</th>
                <th className="p-4 border-b border-main">Status</th>
                <th className="p-4 border-b border-main">Model</th>
                <th className="p-4 border-b border-main">Battery 24h</th>
                <th className="p-4 border-b border-main text-right">Load</th>
                <th className="p-4 border-b border-main text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {filtered.map((d) => {
                const status = getStatus(d)
                const { cpu, battery } = deviceMetrics(d)
                return (
                  <tr
                    key={d.device_id}
                    className="hover:bg-zinc-900/50 transition-colors group"
                  >
                    <td className="p-4 border-b border-main mono text-xs text-zinc-400">
                      #{d.device_id}
                    </td>
                    <td className="p-4 border-b border-main">
                      <span className={`flex items-center gap-2 text-xs font-medium ${status.color}`}>
                        {status.label === 'CRITICAL' ? (
                          <AlertCircle className="w-3 h-3" />
                        ) : (
                          <span className={`w-1.5 h-1.5 ${status.dot} rounded-full`} />
                        )}
                        {status.label}
                      </span>
                    </td>
                    <td className="p-4 border-b border-main text-zinc-300">
                      {d.model || d.name || 'Unknown'}
                      {(d.sdkInt || d.sdk) && (
                        <span className="text-[10px] text-zinc-500 ml-2">
                          SDK {d.sdkInt || d.sdk}
                        </span>
                      )}
                    </td>
                    <td className="p-4 border-b border-main">
                      <Sparkline
                        values={sparklines[d.device_id] || []}
                        color={battery != null && battery < 20 ? '#ef4444' : '#10b981'}
                        width={88}
                        height={22}
                      />
                    </td>
                    <td className="p-4 border-b border-main text-right">
                      <div className="inline-flex items-center gap-4">
                        <div className="flex items-center gap-2">
                          <span className="text-[9px] text-zinc-600 uppercase">CPU</span>
                          <div className="w-16 bg-zinc-800 h-1 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                cpu != null && cpu > 90 ? 'bg-red-500' : 'bg-emerald-500'
                              }`}
                              style={{ width: `${cpu ?? 0}%` }}
                            />
                          </div>
                          <span className="text-[10px] mono w-8 text-right">{cpu != null ? `${Math.round(cpu)}%` : '--'}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[9px] text-zinc-600 uppercase">BAT</span>
                          <div className="w-16 bg-zinc-800 h-1 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                battery != null && battery < 20 ? 'bg-red-500' : 'bg-white'
                              }`}
                              style={{ width: `${battery ?? 0}%` }}
                            />
                          </div>
                          <span className="text-[10px] mono w-8 text-right">{battery != null ? `${battery}%` : '--'}</span>
                        </div>
                      </div>
                    </td>
                    <td className="p-4 border-b border-main text-right">
                      <button
                        onClick={() => navigate(`/node/${d.device_id}`)}
                        className="text-xs font-semibold text-zinc-500 hover:text-white transition-colors"
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
