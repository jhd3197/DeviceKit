import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  Briefcase,
  RefreshCw,
  RotateCcw,
  XCircle,
  Clock,
  Loader2,
  CheckCircle,
  AlertCircle,
  Ban,
  Play,
  CalendarClock,
} from 'lucide-react'
import { api, subscribeToEvents } from '../api'

const STATUS_FILTERS = [
  { key: '', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'running', label: 'Running' },
  { key: 'succeeded', label: 'Succeeded' },
  { key: 'failed', label: 'Failed' },
  { key: 'cancelled', label: 'Cancelled' },
]

const STATUS_STYLE = {
  pending: 'bg-amber-500/10 text-amber-400',
  running: 'bg-blue-500/10 text-blue-400',
  succeeded: 'bg-emerald-500/10 text-emerald-400',
  failed: 'bg-red-500/10 text-red-400',
  cancelled: 'bg-zinc-500/10 text-zinc-400',
}

const STATUS_ICON = {
  pending: Clock,
  running: Loader2,
  succeeded: CheckCircle,
  failed: AlertCircle,
  cancelled: Ban,
}

function fmtTime(epoch) {
  if (!epoch) return '--'
  const d = new Date(Number(epoch) * 1000)
  return d.toLocaleString()
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
        STATUS_STYLE[status] || STATUS_STYLE.cancelled
      }`}
    >
      <Icon className={`w-3 h-3 ${status === 'running' ? 'animate-spin' : ''}`} />
      {status}
    </span>
  )
}

export default function Jobs() {
  const [jobs, setJobs] = useState([])
  const [schedules, setSchedules] = useState([])
  const [stats, setStats] = useState({ by_status: {}, by_kind: {}, total: 0 })
  const [statusFilter, setStatusFilter] = useState('')
  const [kindFilter, setKindFilter] = useState('')
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)
  const esRef = useRef(null)

  const fetchJobs = useCallback(async () => {
    try {
      const [jobsRes, statsRes] = await Promise.all([
        api.listJobs({ status: statusFilter, kind: kindFilter, limit: 100 }),
        api.getJobStats(),
      ])
      setJobs(jobsRes.jobs || [])
      setStats(statsRes || { by_status: {}, by_kind: {}, total: 0 })
    } catch {
      // keep current state on transient errors
    } finally {
      setLoading(false)
    }
  }, [statusFilter, kindFilter])

  const fetchSchedules = useCallback(async () => {
    try {
      const res = await api.listScheduledJobs()
      setSchedules(res.schedules || [])
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    fetchJobs()
    fetchSchedules()
  }, [fetchJobs, fetchSchedules])

  // Live updates: any job transition refreshes the list + stats.
  useEffect(() => {
    const es = subscribeToEvents({
      onJob: () => {
        fetchJobs()
      },
    })
    esRef.current = es
    return () => es.close()
  }, [fetchJobs])

  const doRetry = async (id) => {
    setBusyId(id)
    try {
      await api.retryJob(id)
      await fetchJobs()
    } catch {
      /* noop */
    } finally {
      setBusyId(null)
    }
  }

  const doCancel = async (id) => {
    setBusyId(id)
    try {
      await api.cancelJob(id)
      await fetchJobs()
    } catch {
      /* noop */
    } finally {
      setBusyId(null)
    }
  }

  const runSchedule = async (id) => {
    setBusyId(`sch-${id}`)
    try {
      await api.runScheduledJob(id)
      await Promise.all([fetchJobs(), fetchSchedules()])
    } catch {
      /* noop */
    } finally {
      setBusyId(null)
    }
  }

  const toggleSchedule = async (sch) => {
    setBusyId(`sch-${sch.id}`)
    try {
      await api.setScheduledJobEnabled(sch.id, !sch.enabled)
      await fetchSchedules()
    } catch {
      /* noop */
    } finally {
      setBusyId(null)
    }
  }

  const kinds = Object.keys(stats.by_kind || {}).sort()

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Briefcase className="w-5 h-5 text-emerald-400" />
          <h1 className="text-lg font-bold text-zinc-100">Jobs</h1>
          <span className="text-xs text-zinc-500">
            background work — automation runs, schedules, housekeeping
          </span>
        </div>
        <button
          onClick={() => {
            fetchJobs()
            fetchSchedules()
          }}
          className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-100 border border-main rounded px-2.5 py-1.5"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        {[
          { key: 'total', label: 'Total', value: stats.total || 0, tone: 'text-zinc-100' },
          { key: 'pending', label: 'Pending', value: stats.by_status?.pending || 0, tone: 'text-amber-400' },
          { key: 'running', label: 'Running', value: stats.by_status?.running || 0, tone: 'text-blue-400' },
          { key: 'succeeded', label: 'Succeeded', value: stats.by_status?.succeeded || 0, tone: 'text-emerald-400' },
          { key: 'failed', label: 'Failed', value: stats.by_status?.failed || 0, tone: 'text-red-400' },
          { key: 'cancelled', label: 'Cancelled', value: stats.by_status?.cancelled || 0, tone: 'text-zinc-400' },
        ].map((s) => (
          <div key={s.key} className="bg-hover border border-main rounded-lg p-3">
            <div className="text-[10px] uppercase text-zinc-500 font-bold">{s.label}</div>
            <div className={`text-2xl font-bold ${s.tone}`}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Schedules */}
      <div className="bg-hover border border-main rounded-lg">
        <div className="px-4 py-2.5 border-b border-main flex items-center gap-2">
          <CalendarClock className="w-4 h-4 text-zinc-400" />
          <h2 className="text-sm font-bold text-zinc-200">Schedules</h2>
          <span className="text-[10px] text-zinc-500">{schedules.length} defined</span>
        </div>
        <div className="divide-y divide-zinc-800">
          {schedules.length === 0 ? (
            <div className="px-4 py-6 text-center text-xs text-zinc-500">No schedules</div>
          ) : (
            schedules.map((sch) => (
              <div key={sch.id} className="px-4 py-2.5 flex items-center gap-3 text-xs">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-zinc-200 truncate">{sch.name}</div>
                  <div className="text-[10px] text-zinc-500 mono">
                    {sch.kind} ·{' '}
                    {sch.schedule_kind === 'cron'
                      ? `cron ${sch.cron}`
                      : `every ${sch.interval_seconds}s`}{' '}
                    · next {fmtTime(sch.next_run_at)}
                  </div>
                </div>
                <span
                  className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                    sch.enabled ? 'bg-emerald-500/10 text-emerald-400' : 'bg-zinc-500/10 text-zinc-400'
                  }`}
                >
                  {sch.enabled ? 'enabled' : 'paused'}
                </span>
                <button
                  onClick={() => runSchedule(sch.id)}
                  disabled={busyId === `sch-${sch.id}`}
                  className="flex items-center gap-1 text-zinc-400 hover:text-emerald-400 disabled:opacity-40"
                  title="Run now"
                >
                  <Play className="w-4 h-4" />
                </button>
                <button
                  onClick={() => toggleSchedule(sch)}
                  disabled={busyId === `sch-${sch.id}`}
                  className="text-zinc-400 hover:text-zinc-100 disabled:opacity-40 text-[10px] border border-main rounded px-2 py-1"
                >
                  {sch.enabled ? 'Pause' : 'Resume'}
                </button>
              </div>
            ))
          )}
        </div>
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
        {kinds.length > 0 && (
          <select
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            className="text-xs bg-hover border border-main rounded px-2 py-1.5 text-zinc-300 ml-auto"
          >
            <option value="">All kinds</option>
            {kinds.map((k) => (
              <option key={k} value={k}>
                {k} ({stats.by_kind[k]})
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Jobs table */}
      <div className="bg-hover border border-main rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-zinc-500 border-b border-main">
                <th className="px-4 py-2.5 font-medium">Kind</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Owner</th>
                <th className="px-4 py-2.5 font-medium">Attempts</th>
                <th className="px-4 py-2.5 font-medium">Created</th>
                <th className="px-4 py-2.5 font-medium">Duration</th>
                <th className="px-4 py-2.5 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-zinc-500">
                    <Loader2 className="w-4 h-4 animate-spin inline" /> Loading…
                  </td>
                </tr>
              ) : jobs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-zinc-500">
                    No jobs
                  </td>
                </tr>
              ) : (
                jobs.map((j) => (
                  <React.Fragment key={j.id}>
                    <tr
                      className="border-b border-zinc-800 hover:bg-zinc-800/40 cursor-pointer"
                      onClick={() => setSelected(selected === j.id ? null : j.id)}
                    >
                      <td className="px-4 py-2.5 mono text-zinc-200">{j.kind}</td>
                      <td className="px-4 py-2.5">
                        <StatusBadge status={j.status} />
                      </td>
                      <td className="px-4 py-2.5 text-zinc-400 mono text-[10px]">
                        {j.owner_type ? `${j.owner_type}:${j.owner_id || ''}` : '--'}
                      </td>
                      <td className="px-4 py-2.5 text-zinc-400">
                        {j.attempts}/{j.max_attempts}
                      </td>
                      <td className="px-4 py-2.5 text-zinc-500 mono text-[10px]">
                        {fmtTime(j.created_at)}
                      </td>
                      <td className="px-4 py-2.5 text-zinc-400 mono text-[10px]">
                        {fmtDuration(j.duration)}
                      </td>
                      <td className="px-4 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                        {(j.status === 'failed' || j.status === 'cancelled') && (
                          <button
                            onClick={() => doRetry(j.id)}
                            disabled={busyId === j.id}
                            className="inline-flex items-center gap-1 text-zinc-400 hover:text-emerald-400 disabled:opacity-40 mr-3"
                            title="Retry"
                          >
                            <RotateCcw className="w-4 h-4" />
                          </button>
                        )}
                        {(j.status === 'pending' || j.status === 'running') && (
                          <button
                            onClick={() => doCancel(j.id)}
                            disabled={busyId === j.id}
                            className="inline-flex items-center gap-1 text-zinc-400 hover:text-red-400 disabled:opacity-40"
                            title="Cancel"
                          >
                            <XCircle className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                    {selected === j.id && (
                      <tr className="bg-black/40">
                        <td colSpan={7} className="px-4 py-3">
                          <div className="grid md:grid-cols-2 gap-3 text-[11px]">
                            <div>
                              <div className="text-zinc-500 uppercase font-bold mb-1">Details</div>
                              <div className="mono text-zinc-400 space-y-0.5">
                                <div>id: {j.id}</div>
                                <div>started: {fmtTime(j.started_at)}</div>
                                <div>completed: {fmtTime(j.completed_at)}</div>
                                {j.correlation_id && <div>correlation: {j.correlation_id}</div>}
                              </div>
                            </div>
                            <div>
                              <div className="text-zinc-500 uppercase font-bold mb-1">
                                {j.error_message ? 'Error' : 'Result'}
                              </div>
                              <pre
                                className={`mono text-[10px] whitespace-pre-wrap break-words max-h-40 overflow-auto ${
                                  j.error_message ? 'text-red-400' : 'text-zinc-400'
                                }`}
                              >
                                {j.error_message || JSON.stringify(j.result, null, 2) || '--'}
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
