import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import Sparkline from '../ds/Sparkline'

function getStatus(d) {
  if (!d) return { label: 'OFFLINE', color: 'text-zinc-500', dot: 'bg-zinc-700' }
  if (d.currentPackageName && d.currentPackageName !== 'com.android.launcher3')
    return { label: 'RUNNING', color: 'text-emerald-500', dot: 'bg-emerald-500' }
  return { label: 'IDLE', color: 'text-zinc-500', dot: 'bg-zinc-700' }
}

// The device grid/table — the big one. Shows the live fleet, or the FQL query result set
// when a query is active. Self-contained widget carved from Dashboard.jsx (plan 11); reads
// the shared device list, 24h battery sparklines, and the current query result via props.
export default function DeviceRegistry({ devices = [], sparklines = {}, queryResult }) {
  const navigate = useNavigate()
  const [filter, setFilter] = useState('')

  const queryActive = !!queryResult?.active
  const displayDevices = queryActive && queryResult.matches ? queryResult.matches : devices
  const filtered = displayDevices.filter((d) =>
    (d.device_id || '').toLowerCase().includes(filter.toLowerCase())
  )

  return (
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
  )
}
