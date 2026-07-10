// Device Command History view (plan 07).
//
// Audit trail of commands dispatched to agent devices (GET /device-commands?limit=100).
// Table of recent commands with a color-coded status badge and an expandable row that reveals
// args / result / error. Optional status filter refetches with &status=. Modeled on Jobs.jsx.
import React, { useCallback, useEffect, useState } from 'react'
import {
  History,
  RefreshCw,
  Clock,
  Loader2,
  CheckCircle,
  AlertCircle,
  Ban,
  Play,
} from 'lucide-react'

import { api } from '../api'

const STATUS_FILTERS = [
  { key: '', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'running', label: 'Running' },
  { key: 'completed', label: 'Completed' },
  { key: 'failed', label: 'Failed' },
  { key: 'timeout', label: 'Timeout' },
]

const STATUS_STYLE = {
  pending: 'bg-zinc-500/10 text-zinc-400',
  running: 'bg-blue-500/10 text-blue-400',
  completed: 'bg-emerald-500/10 text-emerald-400',
  failed: 'bg-red-500/10 text-red-400',
  timeout: 'bg-red-500/10 text-red-400',
}

const STATUS_ICON = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle,
  failed: AlertCircle,
  timeout: Ban,
}

function fmtRelative(epoch) {
  if (!epoch) return '--'
  const secs = Math.round(Date.now() / 1000 - Number(epoch))
  if (secs < 0) return 'just now'
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

function fmtTime(epoch) {
  if (!epoch) return '--'
  return new Date(Number(epoch) * 1000).toLocaleString()
}

function fmtDuration(sec) {
  if (sec == null) return '--'
  if (sec < 1) return `${(sec * 1000).toFixed(0)}ms`
  if (sec < 60) return `${sec.toFixed(1)}s`
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}

function StatusBadge({ status }) {
  const Icon = STATUS_ICON[status] || Clock
  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
        STATUS_STYLE[status] || STATUS_STYLE.pending
      }`}
    >
      <Icon className={`w-3 h-3 ${status === 'running' ? 'animate-spin' : ''}`} />
      {status}
    </span>
  )
}

function fmtValue(v) {
  if (v == null) return '--'
  if (typeof v === 'string') return v
  return JSON.stringify(v, null, 2)
}

export default function CommandHistory() {
  const [commands, setCommands] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchCommands = useCallback(async () => {
    try {
      const res = await api.getDeviceCommands({ status: statusFilter, limit: 100 })
      setCommands(res.commands || [])
    } catch {
      // keep current state on transient errors
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    fetchCommands()
  }, [fetchCommands])

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <History className="w-5 h-5 text-emerald-400" />
          <div>
            <h1 className="text-xl font-bold">Command History</h1>
            <p className="text-xs text-zinc-500">
              Audit trail of commands dispatched to agent devices
            </p>
          </div>
        </div>
        <button
          onClick={() => { setLoading(true); fetchCommands() }}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-main text-zinc-400 hover:text-zinc-200"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.key || 'all'}
            onClick={() => setStatusFilter(f.key)}
            className={`text-xs px-3 py-1.5 rounded border ${
              statusFilter === f.key
                ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400'
                : 'border-main text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Commands table */}
      <div className="bg-zinc-900 border border-main rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-zinc-500 border-b border-main">
                <th className="px-4 py-2.5 font-medium">Time</th>
                <th className="px-4 py-2.5 font-medium">Device</th>
                <th className="px-4 py-2.5 font-medium">Command</th>
                <th className="px-4 py-2.5 font-medium">Source</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Duration</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-zinc-500">
                    <Loader2 className="w-4 h-4 animate-spin inline" /> Loading…
                  </td>
                </tr>
              ) : commands.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-zinc-500">
                    <History className="w-6 h-6 mx-auto mb-2 opacity-40" />
                    No commands
                  </td>
                </tr>
              ) : (
                commands.map((c) => (
                  <React.Fragment key={c.id}>
                    <tr
                      className="border-b border-zinc-800 hover:bg-zinc-800/40 cursor-pointer"
                      onClick={() => setSelected(selected === c.id ? null : c.id)}
                    >
                      <td className="px-4 py-2.5 text-zinc-500 mono text-[10px]" title={fmtTime(c.created_at)}>
                        {fmtRelative(c.created_at)}
                      </td>
                      <td className="px-4 py-2.5 text-zinc-400 mono text-[10px]">
                        {c.device_id || '--'}
                      </td>
                      <td className="px-4 py-2.5 mono text-zinc-200">{c.command}</td>
                      <td className="px-4 py-2.5 text-zinc-400 mono text-[10px]">
                        {c.source || '--'}
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusBadge status={c.status} />
                      </td>
                      <td className="px-4 py-2.5 text-zinc-400 mono text-[10px]">
                        {fmtDuration(c.duration)}
                      </td>
                    </tr>
                    {selected === c.id && (
                      <tr className="bg-black/40">
                        <td colSpan={6} className="px-4 py-3">
                          <div className="grid md:grid-cols-3 gap-3 text-[11px]">
                            <div>
                              <div className="text-zinc-500 uppercase font-bold mb-1">Args</div>
                              <pre className="mono text-[10px] whitespace-pre-wrap break-words max-h-40 overflow-auto text-zinc-400">
                                {fmtValue(c.args)}
                              </pre>
                            </div>
                            <div>
                              <div className="text-zinc-500 uppercase font-bold mb-1">Result</div>
                              <pre className="mono text-[10px] whitespace-pre-wrap break-words max-h-40 overflow-auto text-zinc-400">
                                {fmtValue(c.result)}
                              </pre>
                            </div>
                            <div>
                              <div className="text-zinc-500 uppercase font-bold mb-1">Error</div>
                              <pre
                                className={`mono text-[10px] whitespace-pre-wrap break-words max-h-40 overflow-auto ${
                                  c.error ? 'text-red-400' : 'text-zinc-400'
                                }`}
                              >
                                {c.error ? fmtValue(c.error) : '--'}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
