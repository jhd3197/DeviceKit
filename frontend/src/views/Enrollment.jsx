// Agent Enrollment view (plan 07).
//
// Operator-facing pairing UI. Lists agents that have started a pairing handshake and are
// waiting to be claimed (GET /agent-devices/pending, polled every 5s), and lets the operator
// claim one — either from a pending row's Claim button or by typing the 6-char code read off
// the phone screen. Claim POSTs { code, passphrase } to /agent-devices/claim. Modeled on
// Jobs.jsx / Notifications.jsx.
import React, { useCallback, useEffect, useState } from 'react'
import {
  ShieldCheck,
  KeyRound,
  Smartphone,
  Clock,
  Loader2,
  RefreshCw,
  CheckCircle,
  AlertCircle,
} from 'lucide-react'

import { api } from '../api'

function fmtCountdown(expiresAt) {
  if (!expiresAt) return '--'
  const secs = Math.round(Number(expiresAt) * 1000 - Date.now()) / 1000
  if (secs <= 0) return 'expired'
  if (secs < 60) return `${Math.floor(secs)}s`
  const m = Math.floor(secs / 60)
  return `${m}m ${Math.floor(secs % 60)}s`
}

function fmtTime(epoch) {
  if (!epoch) return '--'
  return new Date(Number(epoch) * 1000).toLocaleString()
}

export default function Enrollment() {
  const [pending, setPending] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyCode, setBusyCode] = useState(null)
  const [rowError, setRowError] = useState({}) // code -> error string
  const [now, setNow] = useState(Date.now())

  // Manual claim form
  const [manualCode, setManualCode] = useState('')
  const [manualPass, setManualPass] = useState('')
  const [manualBusy, setManualBusy] = useState(false)
  const [manualError, setManualError] = useState('')
  const [manualOk, setManualOk] = useState('')

  const fetchPending = useCallback(async () => {
    try {
      const res = await api.getPendingAgents()
      setPending(res.pending || [])
    } catch {
      // keep current state on transient errors
    } finally {
      setLoading(false)
    }
  }, [])

  // Poll every 5s for pending agents.
  useEffect(() => {
    fetchPending()
    const id = setInterval(fetchPending, 5000)
    return () => clearInterval(id)
  }, [fetchPending])

  // Tick every second so countdowns stay live.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const claim = async (code, passphrase) => {
    setBusyCode(code)
    setRowError((e) => ({ ...e, [code]: '' }))
    try {
      const res = await api.claimAgent(code, passphrase)
      if (res && res.error) {
        setRowError((e) => ({ ...e, [code]: res.error }))
      } else {
        await fetchPending()
      }
    } catch (err) {
      setRowError((e) => ({ ...e, [code]: err.message || 'Claim failed' }))
    } finally {
      setBusyCode(null)
    }
  }

  const submitManual = async (e) => {
    e.preventDefault()
    const code = manualCode.trim()
    if (!code) return
    setManualBusy(true)
    setManualError('')
    setManualOk('')
    try {
      const res = await api.claimAgent(code, manualPass || undefined)
      if (res && res.error) {
        setManualError(res.error)
      } else {
        setManualOk('Agent claimed')
        setManualCode('')
        setManualPass('')
        await fetchPending()
      }
    } catch (err) {
      setManualError(err.message || 'Claim failed')
    } finally {
      setManualBusy(false)
    }
  }

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-5 h-5 text-emerald-400" />
          <div>
            <h1 className="text-xl font-bold">Enrollment</h1>
            <p className="text-xs text-zinc-500">
              Claim agents waiting to pair — verify the code on the device screen
            </p>
          </div>
        </div>
        <button
          onClick={() => { setLoading(true); fetchPending() }}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-main text-zinc-400 hover:text-zinc-200"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Manual claim form */}
      <div className="border border-main rounded-lg p-4 bg-zinc-900/40 space-y-3">
        <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 flex items-center gap-2">
          <KeyRound className="w-3.5 h-3.5" /> Enter code manually
        </p>
        <form onSubmit={submitManual} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 font-bold mb-1">
              Pairing code
            </label>
            <input
              value={manualCode}
              onChange={(e) => setManualCode(e.target.value.toUpperCase())}
              placeholder="ABC123"
              maxLength={6}
              className="w-40 bg-body border border-main rounded px-3 py-2 text-lg mono tracking-widest text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-emerald-500/50"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 font-bold mb-1">
              Passphrase <span className="text-zinc-600">(optional)</span>
            </label>
            <input
              type="password"
              value={manualPass}
              onChange={(e) => setManualPass(e.target.value)}
              placeholder="••••••"
              className="w-48 bg-body border border-main rounded px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-emerald-500/50"
            />
          </div>
          <button
            type="submit"
            disabled={manualBusy || !manualCode.trim()}
            className="flex items-center gap-1.5 text-xs px-4 py-2 rounded border border-emerald-500/50 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-40"
          >
            {manualBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
            Claim
          </button>
          {manualError && (
            <span className="flex items-center gap-1 text-xs text-red-400">
              <AlertCircle className="w-3.5 h-3.5" /> {manualError}
            </span>
          )}
          {manualOk && (
            <span className="flex items-center gap-1 text-xs text-emerald-400">
              <CheckCircle className="w-3.5 h-3.5" /> {manualOk}
            </span>
          )}
        </form>
      </div>

      {/* Pending list */}
      <div>
        <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 mb-3">
          Pending agents{pending.length > 0 ? ` (${pending.length})` : ''}
        </p>
        {loading ? (
          <div className="bg-hover border border-main rounded-lg px-4 py-10 text-center text-zinc-500">
            <Loader2 className="w-4 h-4 animate-spin inline" /> Loading…
          </div>
        ) : pending.length === 0 ? (
          <div className="bg-hover border border-main rounded-lg px-4 py-12 text-center text-zinc-500">
            <ShieldCheck className="w-6 h-6 mx-auto mb-2 opacity-40" />
            No agents waiting to pair
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {pending.map((p) => {
              const expired = fmtCountdown(p.expires_at) === 'expired'
              return (
                <div
                  key={p.id}
                  className="bg-hover border border-main rounded-lg p-4 space-y-3"
                >
                  <div className="flex items-start gap-3">
                    <div className="w-9 h-9 rounded bg-zinc-800 border border-main flex items-center justify-center shrink-0">
                      <Smartphone className="w-4 h-4 text-zinc-400" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-zinc-100 truncate">
                        {p.info?.model || p.device_id || 'Unknown device'}
                      </div>
                      <div className="text-[10px] text-zinc-500 mono truncate">
                        {p.serial || p.device_id || '--'}
                      </div>
                    </div>
                  </div>

                  <div className="text-center py-2">
                    <div className="text-3xl font-bold mono tracking-[0.3em] text-emerald-400">
                      {p.code}
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-zinc-500 mono">
                    <span className="flex items-center gap-1" title={fmtTime(p.expires_at)}>
                      <Clock className="w-3 h-3" />
                      {expired ? 'expired' : `expires in ${fmtCountdown(p.expires_at)}`}
                    </span>
                    <span title={fmtTime(p.created_at)}>#{p.id}</span>
                  </div>

                  {rowError[p.code] && (
                    <div className="flex items-center gap-1 text-[11px] text-red-400">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {rowError[p.code]}
                    </div>
                  )}

                  <button
                    onClick={() => claim(p.code)}
                    disabled={busyCode === p.code || expired}
                    className="w-full flex items-center justify-center gap-1.5 text-xs px-3 py-2 rounded border border-emerald-500/50 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-40"
                  >
                    {busyCode === p.code ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <ShieldCheck className="w-3.5 h-3.5" />
                    )}
                    Claim
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
