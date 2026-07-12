import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, ChevronRight, RefreshCw } from 'lucide-react'
import { api } from '../../api'

const REFRESH_OPTIONS = [
  { label: 'Off', value: 0 },
  { label: '2s', value: 2 },
  { label: '5s', value: 5 },
  { label: '15s', value: 15 },
]

// Currently-executing automations with live step progress (plan 11 phase 3). There is no
// dedicated run SSE channel, so this widget owns its own polling with a per-widget refresh
// selector (ServerKit pattern). Each row deep-links to the run detail page.
export default function ActiveRuns() {
  const navigate = useNavigate()
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshInterval, setRefreshInterval] = useState(() => {
    const saved = localStorage.getItem('devicekit_active_runs_interval')
    return saved != null ? parseInt(saved, 10) : 5
  })

  const load = useCallback(async () => {
    try {
      const r = await api.getAutomationRuns({ limit: 50 })
      const list = Array.isArray(r) ? r : (r.runs || [])
      setRuns(list.filter(run => run.status === 'running' || run.status === 'queued'))
    } catch {
      // leave the last-known set in place on a transient failure
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (refreshInterval <= 0) return
    const tid = setInterval(load, refreshInterval * 1000)
    return () => clearInterval(tid)
  }, [load, refreshInterval])

  const onIntervalChange = (v) => {
    setRefreshInterval(v)
    localStorage.setItem('devicekit_active_runs_interval', String(v))
  }

  return (
    <div className="bg-card border border-main rounded-lg overflow-hidden">
      <div className="p-4 border-b border-main flex justify-between items-center bg-zinc-900/30">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Play className="w-3.5 h-3.5 text-emerald-500" />
          Active Runs
          {runs.length > 0 && (
            <span className="text-[10px] mono text-zinc-500">{runs.length}</span>
          )}
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="text-zinc-500 hover:text-strong transition-colors"
            title="Refresh now"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <select
            value={refreshInterval}
            onChange={(e) => onIntervalChange(parseInt(e.target.value, 10))}
            className="bg-body border border-main text-[10px] mono rounded px-1.5 py-1 focus:outline-none focus:border-zinc-500"
            title="Auto-refresh interval"
          >
            {REFRESH_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="divide-y divide-zinc-800">
        {loading && runs.length === 0 && (
          <p className="p-6 text-center text-zinc-600 text-xs">Loading runs...</p>
        )}
        {!loading && runs.length === 0 && (
          <p className="p-6 text-center text-zinc-600 text-xs">No automations running.</p>
        )}
        {runs.map(run => {
          const total = run.total_steps || 0
          const done = run.completed_steps || 0
          const pct = total > 0 ? Math.round((done / total) * 100) : 0
          const queued = run.status === 'queued'
          return (
            <button
              key={run.id}
              onClick={() => navigate(`/automations/runs/${run.id}`)}
              className="w-full text-left p-4 hover:bg-zinc-900/50 transition-colors flex items-center gap-4 group"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-zinc-200 truncate">
                    {run.automation_name || 'automation'}
                  </span>
                  <span className={`text-[9px] mono px-1.5 py-0.5 rounded ${
                    queued
                      ? 'text-amber-400 bg-amber-500/10'
                      : 'text-emerald-400 bg-emerald-500/10'
                  }`}>
                    {queued ? 'QUEUED' : 'RUNNING'}
                  </span>
                </div>
                <p className="text-[10px] mono text-zinc-500 mt-0.5 truncate">
                  {run.device_id || 'no device'}
                </p>
                {/* Step progress */}
                <div className="flex items-center gap-2 mt-2">
                  <div className="flex-1 bg-zinc-800 h-1 rounded-full overflow-hidden max-w-[220px]">
                    <div
                      className={`h-full rounded-full transition-all ${queued ? 'bg-zinc-600' : 'bg-emerald-500'}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-[10px] mono text-zinc-500">
                    {done}/{total || '?'}
                  </span>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-300 transition-colors shrink-0" />
            </button>
          )
        })}
      </div>
    </div>
  )
}
