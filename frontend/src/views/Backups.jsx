// Backup / DR view (plan 25 part 6).
//
// Back up DeviceKit's own state (DB + redacted config → signed-manifest tarball), watch the
// verify ladder (listed → hashed → drilled), and run a restore drill that proves the backup
// actually restores — into a throwaway scratch DB, never touching live. restore_confidence
// is the plan-24 doctor check payload. Refetches on the `backup` SSE event.
import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  DatabaseBackup,
  RefreshCw,
  Loader2,
  ShieldCheck,
  PlayCircle,
  Trash2,
  CheckCircle,
  AlertTriangle,
  XCircle,
} from 'lucide-react'

import { api, subscribeToEvents } from '../api'

const LADDER = ['none', 'listed', 'hashed', 'drilled']
const LADDER_STYLE = {
  none: 'text-zinc-500 border-main',
  listed: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
  hashed: 'text-blue-400 border-blue-500/40 bg-blue-500/10',
  drilled: 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10',
}
const CONF_STYLE = { ok: 'text-emerald-400', warn: 'text-amber-400', fail: 'text-red-400' }
const CONF_ICON = { ok: CheckCircle, warn: AlertTriangle, fail: XCircle }

function fmtBytes(n) {
  if (!n) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = n
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(1)} ${u[i]}`
}
function fmtTime(epoch) {
  if (!epoch) return '--'
  return new Date(Number(epoch) * 1000).toLocaleString()
}

export default function Backups() {
  const [backups, setBackups] = useState([])
  const [confidence, setConfidence] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const esRef = useRef(null)

  const refetch = useCallback(async () => {
    try {
      const [bk, conf] = await Promise.all([api.getBackups(), api.getRestoreConfidence()])
      setBackups(bk.backups || [])
      setConfidence(conf)
    } catch {
      // keep state
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])
  useEffect(() => {
    const es = subscribeToEvents({ onBackup: () => refetch() })
    esRef.current = es
    return () => es && es.close()
  }, [refetch])

  const create = async () => {
    setBusy('create')
    try { await api.createBackup() } catch { /* ignore */ }
    setBusy(''); await refetch()
  }
  const drill = async (id) => {
    setBusy(`drill:${id || 'latest'}`)
    try { await api.runBackupDrill(id) } catch { /* ignore */ }
    setBusy(''); await refetch()
  }
  const verify = async (id) => {
    setBusy(`verify:${id}`)
    try { await api.verifyBackup(id) } catch { /* ignore */ }
    setBusy(''); await refetch()
  }
  const remove = async (id) => {
    await api.deleteBackup(id).catch(() => {})
    await refetch()
  }

  const ConfIcon = confidence ? (CONF_ICON[confidence.status] || AlertTriangle) : AlertTriangle

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <DatabaseBackup className="w-5 h-5 text-emerald-400" />
          <div>
            <h1 className="text-xl font-bold">Backup &amp; DR</h1>
            <p className="text-xs text-zinc-500">
              Back up DeviceKit's own state — and prove it restores with a drill
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setLoading(true); refetch() }}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-main text-zinc-400 hover:text-zinc-200"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
          <button
            onClick={create}
            disabled={busy === 'create'}
            className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded border border-emerald-500/50 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-40"
          >
            {busy === 'create' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <DatabaseBackup className="w-3.5 h-3.5" />}
            Back up now
          </button>
        </div>
      </div>

      {/* Restore confidence (plan-24 doctor check) */}
      {confidence && (
        <div className="border border-main rounded-lg p-4 bg-zinc-900/40 flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <ConfIcon className={`w-4 h-4 ${CONF_STYLE[confidence.status] || 'text-zinc-400'}`} />
            <div>
              <div className="text-[10px] uppercase font-bold text-zinc-500">Restore confidence</div>
              <div className={`text-sm font-semibold ${CONF_STYLE[confidence.status] || 'text-zinc-300'}`}>
                {confidence.detail}
              </div>
            </div>
          </div>
          <button
            onClick={() => drill()}
            disabled={busy.startsWith('drill')}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-blue-500/50 bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 disabled:opacity-40"
          >
            {busy.startsWith('drill') ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
            Run restore drill
          </button>
        </div>
      )}

      {loading ? (
        <div className="bg-zinc-900 border border-main rounded-lg px-4 py-10 text-center text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin inline" /> Loading…
        </div>
      ) : backups.length === 0 ? (
        <div className="bg-zinc-900 border border-main rounded-lg px-4 py-12 text-center text-zinc-500">
          <DatabaseBackup className="w-6 h-6 mx-auto mb-2 opacity-40" />
          No backups yet — create one to start
        </div>
      ) : (
        <div className="bg-zinc-900 border border-main rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] uppercase text-zinc-500 border-b border-main">
                  <th className="text-left font-bold px-4 py-2">Backup</th>
                  <th className="text-left font-bold px-4 py-2">Size</th>
                  <th className="text-left font-bold px-4 py-2">Verify</th>
                  <th className="text-left font-bold px-4 py-2">Drill</th>
                  <th className="text-right font-bold px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {backups.map((b) => (
                  <tr key={b.id} className="border-b border-main/50 hover:bg-zinc-800/40">
                    <td className="px-4 py-2">
                      <div className="mono text-zinc-200">{b.id}</div>
                      <div className="text-[10px] text-zinc-500">{fmtTime(b.created_at)}</div>
                    </td>
                    <td className="px-4 py-2 mono text-zinc-400">{fmtBytes(b.size_bytes)}</td>
                    <td className="px-4 py-2">
                      <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${LADDER_STYLE[b.verify_level] || 'text-zinc-400 border-main'}`}>
                        {b.verify_level}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      {b.drill_status ? (
                        <span className={b.drill_status === 'passed' ? 'text-emerald-400' : b.drill_status === 'skipped_no_space' ? 'text-amber-400' : 'text-red-400'}>
                          {b.drill_status}
                        </span>
                      ) : <span className="text-zinc-600">—</span>}
                    </td>
                    <td className="px-4 py-2 text-right whitespace-nowrap">
                      <button onClick={() => verify(b.id)} disabled={busy === `verify:${b.id}`}
                        className="text-[11px] px-2 py-1 rounded border border-main text-zinc-300 hover:bg-zinc-800 mr-1">
                        Verify
                      </button>
                      <button onClick={() => drill(b.id)} disabled={busy === `drill:${b.id}`}
                        className="text-[11px] px-2 py-1 rounded border border-blue-500/40 text-blue-400 hover:bg-blue-500/10 mr-1">
                        <PlayCircle className="w-3 h-3 inline" /> Drill
                      </button>
                      <button onClick={() => remove(b.id)} className="text-zinc-500 hover:text-red-400 align-middle">
                        <Trash2 className="w-3.5 h-3.5 inline" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
