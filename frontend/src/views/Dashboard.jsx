import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, AlertCircle } from 'lucide-react'
import { api } from '../api'

const REFRESH_INTERVAL = 10000

export default function Dashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [devices, setDevices] = useState([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      const [s, d] = await Promise.all([api.getStats(), api.getDevices()])
      setStats(s)
      setDevices(d.devices || [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, REFRESH_INTERVAL)
    return () => clearInterval(id)
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
          <div className="flex items-center gap-2 text-[10px] mono text-emerald-500 bg-emerald-500/10 px-2 py-1 rounded border border-emerald-500/20">
            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
            ALL SYSTEMS OPERATIONAL
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
                const load = Math.floor(Math.random() * 80 + 10) // placeholder load
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
                      {d.name || 'Unknown'}
                      {d.sdkInt && (
                        <span className="text-[10px] text-zinc-500 ml-2">
                          SDK {d.sdkInt}
                        </span>
                      )}
                    </td>
                    <td className="p-4 border-b border-main text-right">
                      <div className="inline-flex items-center gap-3">
                        <div className="w-24 bg-zinc-800 h-1 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              load > 90 ? 'bg-red-500' : 'bg-white'
                            }`}
                            style={{ width: `${load}%` }}
                          />
                        </div>
                        <span className="text-[10px] mono">{load}%</span>
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
