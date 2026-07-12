import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ChevronRight, RefreshCw } from 'lucide-react'
import { api } from '../../api'

const LIMIT = 6

function timeAgo(ts) {
  if (!ts) return ''
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

// Last N failed automation runs (plan 11 phase 3). Each row deep-links to the run detail
// page, where the debug bundle and failure screenshots live. Self-fetching, refreshed on a
// slow poll — failures are not high-frequency.
export default function RecentFailures() {
  const navigate = useNavigate()
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const r = await api.getAutomationRuns({ limit: 50 })
      const list = Array.isArray(r) ? r : (r.runs || [])
      setRuns(list.filter(run => run.status === 'failed').slice(0, LIMIT))
    } catch {
      // keep last-known set
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const tid = setInterval(load, 30000)
    return () => clearInterval(tid)
  }, [load])

  return (
    <div className="bg-card border border-main rounded-lg overflow-hidden">
      <div className="p-4 border-b border-main flex justify-between items-center bg-zinc-900/30">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
          Recent Failures
          {runs.length > 0 && (
            <span className="text-[10px] mono text-zinc-500">{runs.length}</span>
          )}
        </h3>
        <button
          onClick={load}
          className="text-zinc-500 hover:text-strong transition-colors"
          title="Refresh now"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="divide-y divide-zinc-800">
        {loading && runs.length === 0 && (
          <p className="p-6 text-center text-zinc-600 text-xs">Loading failures...</p>
        )}
        {!loading && runs.length === 0 && (
          <p className="p-6 text-center text-zinc-600 text-xs">No recent failures.</p>
        )}
        {runs.map(run => (
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
                <span className="text-[9px] mono px-1.5 py-0.5 rounded text-red-400 bg-red-500/10">
                  FAILED
                </span>
                <span className="text-[10px] mono text-zinc-600 ml-auto shrink-0">
                  {timeAgo(run.finished_at || run.started_at)}
                </span>
              </div>
              <p className="text-[10px] mono text-zinc-500 mt-0.5 truncate">
                {run.device_id || 'no device'}
              </p>
              {run.error && (
                <p className="text-[10px] text-red-400/80 mono mt-1 truncate">
                  {run.error}
                </p>
              )}
            </div>
            <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-300 transition-colors shrink-0" />
          </button>
        ))}
      </div>
    </div>
  )
}
