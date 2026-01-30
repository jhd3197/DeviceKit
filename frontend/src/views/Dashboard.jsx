import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, AlertCircle, Smartphone, X } from 'lucide-react'
import { api, subscribeToEvents } from '../api'

export default function Dashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [devices, setDevices] = useState([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sseConnected, setSseConnected] = useState(false)
  const [fleetHealth, setFleetHealth] = useState(null)
  const [toasts, setToasts] = useState([])

  const fetchData = useCallback(async () => {
    try {
      const [s, d, fh] = await Promise.all([api.getStats(), api.getDevices(), api.getFleetHealth().catch(() => null)])
      setStats(s)
      setDevices(d.devices || [])
      setFleetHealth(fh)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => { fetchData() }, [fetchData])

  // SSE subscription for real-time updates
  useEffect(() => {
    const es = subscribeToEvents({
      onDeviceState: (data) => {
        setDevices(prev => prev.map(d =>
          d.device_id === data.device_id
            ? { ...d, metrics: data.state?.metrics, cpu_percent: data.state?.metrics?.cpu_percent, battery_level: data.state?.metrics?.battery_level, lastUpdate: Date.now() }
            : d
        ))
      },
      onDeviceConnected: () => {
        fetchData()
      },
      onDeviceDisconnected: (data) => {
        setDevices(prev => prev.map(d =>
          d.device_id === data.device_id ? { ...d, online: false } : d
        ))
      },
      onAlert: () => {
        setStats(prev => prev ? { ...prev, active_alerts: (prev.active_alerts || 0) + 1 } : prev)
      },
      onDeviceNew: (data) => {
        const id = `toast-${Date.now()}`
        setToasts(prev => [...prev, { id, device_id: data.device_id, info: data.info }])
        setTimeout(() => {
          setToasts(prev => prev.filter(t => t.id !== id))
        }, 15000)
      },
      onError: () => {
        setSseConnected(false)
      },
    })
    es.addEventListener('connected', () => setSseConnected(true))
    return () => es.close()
  }, [fetchData])

  const filtered = devices.filter((d) =>
    (d.device_id || '').toLowerCase().includes(filter.toLowerCase())
  )

  const getStatus = (d) => {
    if (!d) return { label: 'OFFLINE', color: 'text-zinc-500', dot: 'bg-zinc-700' }
    if (d.currentPackageName && d.currentPackageName !== 'com.android.launcher3')
      return { label: 'RUNNING', color: 'text-emerald-500', dot: 'bg-emerald-500' }
    return { label: 'IDLE', color: 'text-zinc-500', dot: 'bg-zinc-700' }
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-zinc-500 text-sm mono">Loading fleet data...</span>
      </div>
    )
  }

  return (
    <>
      {/* Header */}
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-black/50 backdrop-blur-md shrink-0">
        <div className="flex items-center gap-2 text-xs font-medium text-zinc-500">
          <span>Infrastructure</span>
          <ChevronRight className="w-3 h-3" />
          <span className="text-zinc-200">Fleet Overview</span>
        </div>
        <div className="flex items-center gap-4">
          <div className={`flex items-center gap-2 text-[10px] mono px-2 py-1 rounded border ${
            sseConnected
              ? 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20'
              : 'text-red-400 bg-red-500/10 border-red-500/20'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${sseConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
            {sseConnected ? 'LIVE' : 'RECONNECTING'}
          </div>
          <button className="bg-white text-black text-xs font-bold px-4 py-1.5 rounded hover:bg-zinc-200 transition-colors">
            Deploy Update
          </button>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8 space-y-8 max-w-7xl">
        {error && (
          <div className="bg-red-950/50 border border-red-900/50 rounded-lg p-3 text-xs text-red-400">
            {error}
          </div>
        )}

        {/* Metric Cards */}
        <div className="grid grid-cols-4 gap-4">
          <MetricCard label="Global Fleet" value={stats?.fleet_count ?? 0} unit="Nodes" />
          <MetricCard
            label="Active Utilization"
            value={`${stats?.utilization ?? 0}%`}
            valueClass="text-emerald-500"
          />
          <MetricCard label="Avg Response" value={`${stats?.avg_response_ms ?? 0}ms`} />
          <MetricCard
            label="System Health"
            value={stats?.health ?? 'Unknown'}
            valueClass={
              stats?.health === 'Healthy' ? 'text-emerald-400' : 'text-red-400'
            }
          />
        </div>

        {/* Fleet Health Cards */}
        {fleetHealth && (
          <>
            <div className="grid grid-cols-4 gap-4">
              <MetricCard
                label="Avg CPU"
                value={`${fleetHealth.avg_cpu}%`}
                valueClass={fleetHealth.avg_cpu > 80 ? 'text-red-400' : 'text-emerald-400'}
              />
              <MetricCard
                label="Avg Battery"
                value={`${fleetHealth.avg_battery}%`}
                valueClass={fleetHealth.avg_battery < 20 ? 'text-red-400' : 'text-white'}
              />
              <MetricCard
                label="Total RAM"
                value={`${(fleetHealth.total_ram_used_mb / 1024).toFixed(1)}`}
                unit={`/ ${(fleetHealth.total_ram_total_mb / 1024).toFixed(1)} GB`}
              />
              <MetricCard
                label="Avg Temp"
                value={`${fleetHealth.avg_temperature}°C`}
                valueClass={fleetHealth.avg_temperature > 45 ? 'text-red-400' : 'text-zinc-200'}
              />
            </div>

            {/* Health Distribution */}
            {(() => {
              const dist = fleetHealth.health_distribution || {}
              const total = (dist.healthy || 0) + (dist.warning || 0) + (dist.critical || 0)
              if (total === 0) return null
              return (
                <div className="bg-card border border-main p-4 rounded-lg">
                  <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">
                    Fleet Health Distribution
                  </p>
                  <div className="flex h-3 rounded-full overflow-hidden bg-zinc-900">
                    {dist.healthy > 0 && (
                      <div
                        className="bg-emerald-500 transition-all"
                        style={{ width: `${(dist.healthy / total) * 100}%` }}
                      />
                    )}
                    {dist.warning > 0 && (
                      <div
                        className="bg-amber-500 transition-all"
                        style={{ width: `${(dist.warning / total) * 100}%` }}
                      />
                    )}
                    {dist.critical > 0 && (
                      <div
                        className="bg-red-500 transition-all"
                        style={{ width: `${(dist.critical / total) * 100}%` }}
                      />
                    )}
                  </div>
                  <div className="flex gap-4 mt-2 text-[10px]">
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-emerald-500" /> Healthy: {dist.healthy}
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-amber-500" /> Warning: {dist.warning}
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-red-500" /> Critical: {dist.critical}
                    </span>
                  </div>
                </div>
              )
            })()}
          </>
        )}

        {/* Node Registry Table */}
        <div className="bg-card border border-main rounded-lg overflow-hidden">
          <div className="p-4 border-b border-main flex justify-between items-center bg-zinc-900/30">
            <h3 className="text-sm font-semibold">Active Node Registry</h3>
            <input
              type="text"
              placeholder="Filter by ID..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="bg-black border border-main px-3 py-1 text-xs rounded focus:outline-none focus:border-zinc-500 w-48"
            />
          </div>
          <table className="w-full text-left border-collapse">
            <thead className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest bg-zinc-900/20">
              <tr>
                <th className="p-4 border-b border-main">Node Identifier</th>
                <th className="p-4 border-b border-main">Status</th>
                <th className="p-4 border-b border-main">Device Model</th>
                <th className="p-4 border-b border-main text-right">Resource Load</th>
                <th className="p-4 border-b border-main text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {filtered.map((d) => {
                const status = getStatus(d)
                const cpu = d.cpu_percent ?? d.metrics?.cpu_percent ?? null
                const battery = d.battery_level ?? d.metrics?.battery_level ?? null
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
                    <td className="p-4 border-b border-main text-right">
                      <div className="inline-flex items-center gap-4">
                        {/* CPU bar */}
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
                        {/* Battery bar */}
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
                        Terminal
                      </button>
                    </td>
                  </tr>
                )
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-zinc-600 text-xs">
                    {devices.length === 0
                      ? 'No devices connected. Connect an Android device via USB.'
                      : 'No devices match filter.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Auto-onboarding toasts */}
      {toasts.length > 0 && (
        <div className="fixed bottom-6 right-6 z-50 space-y-2">
          {toasts.map((t) => (
            <div
              key={t.id}
              className="bg-blue-950 border border-blue-800/50 rounded-lg p-4 flex items-center gap-3 shadow-lg min-w-[300px] animate-[fadeIn_0.3s_ease-out]"
            >
              <Smartphone className="w-5 h-5 text-blue-400 shrink-0" />
              <div className="flex-1">
                <p className="text-xs font-semibold text-blue-200">New device detected</p>
                <p className="text-[10px] mono text-blue-400 mt-0.5">{t.device_id}</p>
              </div>
              <button
                onClick={async () => {
                  try { await api.onboardDevice(t.device_id) } catch {}
                  setToasts(prev => prev.filter(x => x.id !== t.id))
                }}
                className="bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-bold px-3 py-1 rounded transition-colors shrink-0"
              >
                Install Agent
              </button>
              <button
                onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))}
                className="text-blue-600 hover:text-blue-400 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function MetricCard({ label, value, unit, valueClass = '' }) {
  return (
    <div className="bg-card border border-main p-4 rounded-lg">
      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
        {label}
      </p>
      <div className="flex items-baseline gap-2 mt-1">
        <span className={`text-2xl font-semibold italic ${valueClass}`}>{value}</span>
        {unit && <span className="text-[10px] text-zinc-600 mono">{unit}</span>}
      </div>
    </div>
  )
}
