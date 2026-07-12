// Audit log pane (plan 20, admin-only, read-only): a filterable view of the backend
// audit trail. Rows are appended server-side for security-relevant actions; this pane
// only reads them via api.getAuditLog().
import React, { useEffect, useState, useCallback } from 'react'
import { History, Filter, Loader2, RefreshCw } from 'lucide-react'
import { Pane, Select } from './fields'
import { api } from '../../api'

const LIMIT_OPTIONS = [
  { value: '50', label: '50 rows' },
  { value: '100', label: '100 rows' },
  { value: '250', label: '250 rows' },
]

function fmtTime(ts) {
  if (!ts) return ''
  const n = Number(ts)
  if (!Number.isFinite(n)) return String(ts)
  return new Date(n * 1000).toLocaleString()
}

function statusClass(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'ok' || s === 'success' || s === 'allowed') return 'text-emerald-400'
  if (s === 'error' || s === 'fail' || s === 'failed' || s === 'denied') return 'text-red-400'
  return 'text-zinc-400'
}

export default function AuditLog({ settings, save, register }) {
  const reg = register || (() => ({}))
  const [rows, setRows] = useState([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [action, setAction] = useState('')
  const [limit, setLimit] = useState('100')

  const load = useCallback(async (params) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.getAuditLog(params)
      setRows(res.audit_log || [])
      setCount(res.count ?? (res.audit_log || []).length)
    } catch (e) {
      setError(e.message || 'Failed to load audit log')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load({ limit: 100 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refresh = () => load({ limit: Number(limit), action: action.trim() || undefined })

  return (
    <Pane
      title="Audit log"
      description="Security-relevant actions recorded by the backend: who did what, from where, and whether it succeeded. Admin-only and read-only."
    >
      {/* Filter bar */}
      <div className="flex items-center gap-2" {...reg('audit-log')}>
        <div className="relative flex-1">
          <Filter className="w-4 h-4 text-zinc-600 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={action}
            onChange={(e) => setAction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') refresh()
            }}
            placeholder="Filter by action (e.g. login, user.create)"
            className="w-full bg-black border border-alt rounded-md pl-9 pr-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-accent"
          />
        </div>
        <div className="w-32 shrink-0">
          <Select value={limit} onChange={setLimit} options={LIMIT_OPTIONS} />
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-1.5 border border-alt rounded-md px-3 py-1.5 text-sm text-zinc-200 hover:text-white disabled:opacity-40 shrink-0"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          Refresh
        </button>
      </div>

      {error && <div className="text-sm text-red-400">{error}</div>}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-500 py-6">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading audit log…
        </div>
      ) : rows.length === 0 ? (
        <div className="flex items-center gap-2 rounded-md border border-main bg-zinc-950 px-4 py-6 text-sm text-zinc-500">
          <History className="w-4 h-4" /> No audit entries match.
        </div>
      ) : (
        <div className="rounded-md border border-main overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-zinc-950 text-left text-xs uppercase tracking-wide text-zinc-500">
                  <th className="px-3 py-2 font-medium">Time</th>
                  <th className="px-3 py-2 font-medium">Who</th>
                  <th className="px-3 py-2 font-medium">Action</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {rows.map((r) => (
                  <tr key={r.id} className="bg-black hover:bg-zinc-900/40">
                    <td className="px-3 py-2 text-zinc-400 whitespace-nowrap">{fmtTime(r.created_at)}</td>
                    <td className="px-3 py-2 text-zinc-200 whitespace-nowrap">
                      {r.username || r.principal_kind || '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-zinc-200">{r.action}</td>
                    <td className={`px-3 py-2 whitespace-nowrap ${statusClass(r.status)}`}>
                      {r.status || '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-zinc-500 whitespace-nowrap">
                      {r.ip || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-main bg-zinc-950 px-3 py-2 text-xs text-zinc-500">
            Showing {rows.length} of {count} entries
          </div>
        </div>
      )}
    </Pane>
  )
}
