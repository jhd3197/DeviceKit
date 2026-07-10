import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, AlertCircle, Smartphone, X, Search, Play, Save, BookmarkPlus, Download, Zap, ChevronDown, Trash2 } from 'lucide-react'
import { api, subscribeToEvents } from '../api'
import ExtensionSlot from '../extensions/ExtensionSlot'
import Sparkline from '../components/ds/Sparkline'

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
  const [fleetAiCost, setFleetAiCost] = useState(0)
  const [sparklines, setSparklines] = useState({}) // device_id -> [battery %] over 24h (plan 08)

  // Fleet Query state
  const [queryExpr, setQueryExpr] = useState('')
  const [queryActive, setQueryActive] = useState(false)
  const [queryMatches, setQueryMatches] = useState(null)
  const [queryError, setQueryError] = useState(null)
  const [queryLoading, setQueryLoading] = useState(false)
  const [queryFields, setQueryFields] = useState({})
  const [presetQueries, setPresetQueries] = useState([])
  const [savedQueries, setSavedQueries] = useState([])
  const [showPresets, setShowPresets] = useState(false)
  const [showSaved, setShowSaved] = useState(false)
  const [showAutocomplete, setShowAutocomplete] = useState(false)
  const [showBulkAction, setShowBulkAction] = useState(false)
  const queryInputRef = useRef(null)
  const presetsRef = useRef(null)
  const savedRef = useRef(null)

  // Load query metadata on mount
  useEffect(() => {
    api.getQueryFields().then(r => setQueryFields(r.fields || {})).catch(() => {})
    api.getQueryPresets().then(r => setPresetQueries(r.presets || [])).catch(() => {})
    api.getSavedQueries().then(r => setSavedQueries(r.queries || [])).catch(() => {})
  }, [])

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e) => {
      if (presetsRef.current && !presetsRef.current.contains(e.target)) setShowPresets(false)
      if (savedRef.current && !savedRef.current.contains(e.target)) setShowSaved(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const executeQuery = async (expr) => {
    const q = (expr ?? queryExpr).trim()
    if (!q) {
      setQueryActive(false)
      setQueryMatches(null)
      setQueryError(null)
      return
    }
    setQueryLoading(true)
    setQueryError(null)
    try {
      const result = await api.fleetQuery(q)
      setQueryMatches(result.matches || [])
      setQueryActive(true)
    } catch (e) {
      setQueryError(e.message || 'Query failed')
      setQueryMatches(null)
    } finally {
      setQueryLoading(false)
    }
  }

  const clearQuery = () => {
    setQueryExpr('')
    setQueryActive(false)
    setQueryMatches(null)
    setQueryError(null)
  }

  const saveCurrentQuery = async () => {
    const name = prompt('Save query as:')
    if (!name) return
    try {
      const q = await api.createSavedQuery({ name, expression: queryExpr })
      setSavedQueries(prev => [...prev, q])
    } catch {}
  }

  const deleteSavedQuery = async (id) => {
    try {
      await api.deleteSavedQuery(id)
      setSavedQueries(prev => prev.filter(q => q.id !== id))
    } catch {}
  }

  const exportCsv = async () => {
    try {
      const resp = await fetch(`/api/fleet/query?q=${encodeURIComponent(queryExpr)}&format=csv`)
      const text = await resp.text()
      const blob = new Blob([text], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'fleet_query.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch {}
  }

  const runBulkAction = async (action, params = {}) => {
    if (!queryExpr.trim()) return
    try {
      const result = await api.fleetQueryBulkAction(queryExpr, action, params)
      alert(`Bulk ${action}: ${result.succeeded}/${result.total_matched} succeeded`)
      setShowBulkAction(false)
    } catch (e) {
      alert(`Bulk action failed: ${e.message}`)
    }
  }

  // Autocomplete suggestions based on cursor position
  const getAutocompleteSuggestions = () => {
    const val = queryExpr.trim()
    const parts = val.split(/\s+/)
    const last = parts[parts.length - 1]?.toLowerCase() || ''
    if (!last) return Object.keys(queryFields)
    return Object.keys(queryFields).filter(f => f.startsWith(last))
  }

  const fetchData = useCallback(async () => {
    try {
      const [s, d, fh, agentStatuses] = await Promise.all([
        api.getStats(),
        api.getDevices(),
        api.getFleetHealth().catch(() => null),
        api.getAgentStatusAll().catch(() => ({})),
      ])
      setStats(s)
      setDevices(d.devices || [])
      setFleetHealth(fh)
      setError(null)

      // Aggregate AI cost from all active agents
      let totalCost = 0
      if (agentStatuses && typeof agentStatuses === 'object') {
        for (const status of Object.values(agentStatuses)) {
          if (status?.usage?.total_cost) {
            totalCost += status.usage.total_cost
          }
        }
      }
      setFleetAiCost(totalCost)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => { fetchData() }, [fetchData])

  // Battery sparklines for the fleet (24h) — one cheap batch call, refreshed periodically.
  useEffect(() => {
    const loadSparks = () => {
      api.getFleetSparklines('battery_pct', null, '24h')
        .then((r) => setSparklines(r.sparklines || {}))
        .catch(() => {})
    }
    loadSparks()
    const tid = setInterval(loadSparks, 60000)
    return () => clearInterval(tid)
  }, [])

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

  const displayDevices = queryActive && queryMatches ? queryMatches : devices
  const filtered = displayDevices.filter((d) =>
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

        {/* Extension widgets contributed to the dashboard top (plan 04) */}
        <ExtensionSlot name="dashboard.top" className="grid gap-4 md:grid-cols-2" />

        {/* Metric Cards */}
        <div className="grid grid-cols-5 gap-4">
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
          <MetricCard
            label="Fleet AI Cost"
            value={`$${fleetAiCost.toFixed(2)}`}
            valueClass={fleetAiCost > 0 ? 'text-blue-400' : 'text-zinc-400'}
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

        {/* Fleet Query Bar */}
        <div className="bg-card border border-main rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Search className="w-4 h-4 text-zinc-500 shrink-0" />
            <div className="relative flex-1">
              <input
                ref={queryInputRef}
                type="text"
                placeholder='Fleet query — e.g. battery < 20 AND online = true'
                value={queryExpr}
                onChange={(e) => {
                  setQueryExpr(e.target.value)
                  setShowAutocomplete(true)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { executeQuery(); setShowAutocomplete(false) }
                  if (e.key === 'Escape') { setShowAutocomplete(false) }
                }}
                onFocus={() => setShowAutocomplete(true)}
                onBlur={() => setTimeout(() => setShowAutocomplete(false), 200)}
                className="w-full bg-black border border-main px-3 py-1.5 text-xs mono rounded focus:outline-none focus:border-zinc-500"
              />
              {showAutocomplete && queryExpr && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-zinc-900 border border-main rounded shadow-lg z-20 max-h-48 overflow-y-auto">
                  {getAutocompleteSuggestions().map(field => (
                    <button
                      key={field}
                      className="w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-800 flex justify-between"
                      onMouseDown={() => {
                        const parts = queryExpr.split(/\s+/)
                        parts[parts.length - 1] = field
                        setQueryExpr(parts.join(' ') + ' ')
                        setShowAutocomplete(false)
                        queryInputRef.current?.focus()
                      }}
                    >
                      <span className="mono text-zinc-200">{field}</span>
                      <span className="text-zinc-600 text-[10px]">{queryFields[field]}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={() => executeQuery()}
              disabled={queryLoading || !queryExpr.trim()}
              className="bg-white text-black text-xs font-bold px-3 py-1.5 rounded hover:bg-zinc-200 transition-colors disabled:opacity-40 flex items-center gap-1.5"
            >
              <Play className="w-3 h-3" />
              {queryLoading ? 'Running...' : 'Run'}
            </button>
            {queryActive && (
              <button
                onClick={clearQuery}
                className="text-zinc-500 hover:text-white text-xs px-2 py-1.5 rounded border border-main hover:border-zinc-600 transition-colors"
              >
                Clear
              </button>
            )}
          </div>

          {/* Query toolbar */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Presets dropdown */}
            <div className="relative" ref={presetsRef}>
              <button
                onClick={() => { setShowPresets(!showPresets); setShowSaved(false) }}
                className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 border border-main px-2 py-1 rounded transition-colors"
              >
                <Zap className="w-3 h-3" /> Presets <ChevronDown className="w-2.5 h-2.5" />
              </button>
              {showPresets && (
                <div className="absolute top-full left-0 mt-1 bg-zinc-900 border border-main rounded shadow-lg z-20 w-64">
                  {presetQueries.map((p, i) => (
                    <button
                      key={i}
                      className="w-full text-left px-3 py-2 text-xs hover:bg-zinc-800 border-b border-main last:border-0"
                      onClick={() => { setQueryExpr(p.expression); setShowPresets(false); executeQuery(p.expression) }}
                    >
                      <span className="text-zinc-200 font-medium">{p.name}</span>
                      <span className="block text-[10px] text-zinc-600 mono mt-0.5">{p.expression}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Saved queries dropdown */}
            <div className="relative" ref={savedRef}>
              <button
                onClick={() => { setShowSaved(!showSaved); setShowPresets(false) }}
                className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 border border-main px-2 py-1 rounded transition-colors"
              >
                <Save className="w-3 h-3" /> Saved <ChevronDown className="w-2.5 h-2.5" />
              </button>
              {showSaved && (
                <div className="absolute top-full left-0 mt-1 bg-zinc-900 border border-main rounded shadow-lg z-20 w-72">
                  {savedQueries.length === 0 && (
                    <p className="px-3 py-2 text-[10px] text-zinc-600">No saved queries</p>
                  )}
                  {savedQueries.map(q => (
                    <div key={q.id} className="flex items-center border-b border-main last:border-0">
                      <button
                        className="flex-1 text-left px-3 py-2 text-xs hover:bg-zinc-800"
                        onClick={() => { setQueryExpr(q.expression); setShowSaved(false); executeQuery(q.expression) }}
                      >
                        <span className="text-zinc-200 font-medium">{q.name}</span>
                        <span className="block text-[10px] text-zinc-600 mono mt-0.5">{q.expression}</span>
                      </button>
                      <button
                        onClick={() => deleteSavedQuery(q.id)}
                        className="p-2 text-zinc-600 hover:text-red-400 transition-colors"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {queryExpr.trim() && (
              <>
                <button
                  onClick={saveCurrentQuery}
                  className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 border border-main px-2 py-1 rounded transition-colors"
                >
                  <BookmarkPlus className="w-3 h-3" /> Save Query
                </button>
                {queryActive && (
                  <>
                    <button
                      onClick={exportCsv}
                      className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 border border-main px-2 py-1 rounded transition-colors"
                    >
                      <Download className="w-3 h-3" /> Export CSV
                    </button>
                    <div className="relative">
                      <button
                        onClick={() => setShowBulkAction(!showBulkAction)}
                        className="flex items-center gap-1 text-[10px] text-amber-500 hover:text-amber-300 border border-amber-900/50 px-2 py-1 rounded transition-colors"
                      >
                        <Zap className="w-3 h-3" /> Bulk Action <ChevronDown className="w-2.5 h-2.5" />
                      </button>
                      {showBulkAction && (
                        <div className="absolute top-full left-0 mt-1 bg-zinc-900 border border-main rounded shadow-lg z-20 w-48">
                          {['reboot', 'lock', 'unlock', 'add_tag', 'add_to_group'].map(action => (
                            <button
                              key={action}
                              className="w-full text-left px-3 py-2 text-xs hover:bg-zinc-800 border-b border-main last:border-0 text-zinc-300"
                              onClick={() => {
                                let params = {}
                                if (action === 'add_tag') {
                                  const tag = prompt('Tag name:')
                                  if (!tag) return
                                  params = { tag }
                                }
                                if (action === 'add_to_group') {
                                  const gid = prompt('Group ID:')
                                  if (!gid) return
                                  params = { group_id: gid }
                                }
                                runBulkAction(action, params)
                              }}
                            >
                              {action.replace(/_/g, ' ')}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </>
                )}
              </>
            )}

            {queryActive && queryMatches && (
              <span className="text-[10px] text-zinc-500 ml-auto">
                {queryMatches.length} device{queryMatches.length !== 1 ? 's' : ''} matched
              </span>
            )}
          </div>

          {queryError && (
            <div className="bg-red-950/50 border border-red-900/50 rounded p-2 text-xs text-red-400 mono">
              {queryError}
            </div>
          )}
        </div>

        {/* Node Registry Table */}
        <div className="bg-card border border-main rounded-lg overflow-hidden">
          <div className="p-4 border-b border-main flex justify-between items-center bg-zinc-900/30">
            <h3 className="text-sm font-semibold">
              {queryActive ? 'Query Results' : 'Active Node Registry'}
            </h3>
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
                <th className="p-4 border-b border-main">Battery 24h</th>
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
                  <td colSpan={6} className="p-8 text-center text-zinc-600 text-xs">
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
