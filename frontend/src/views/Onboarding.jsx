// Onboarding view (plan 25 part 4).
//
// The formal enrollment lifecycle — pending → validating → provisioning → ready | failed —
// with each device's ordered progress log. A newly-registered device shows up here and
// advances on the job bus; a ready device has had its group policy applied (plan 23).
// Backed by /onboarding; refetches on the `onboarding` SSE event.
import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  ClipboardList,
  RefreshCw,
  Loader2,
  CheckCircle,
  XCircle,
  CircleDashed,
  RotateCw,
  Smartphone,
} from 'lucide-react'

import { api, subscribeToEvents } from '../api'

const STATE_STYLE = {
  pending: 'text-zinc-400 border-main',
  validating: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
  provisioning: 'text-blue-400 border-blue-500/40 bg-blue-500/10',
  ready: 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10',
  failed: 'text-red-400 border-red-500/40 bg-red-500/10',
}
const ORDER = ['validate', 'provision', 'finalize']

function StepDot({ status }) {
  if (status === 'ok') return <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
  if (status === 'error') return <XCircle className="w-3.5 h-3.5 text-red-400" />
  return <CircleDashed className="w-3.5 h-3.5 text-zinc-500" />
}

function fmtTime(epoch) {
  if (!epoch) return '--'
  return new Date(Number(epoch) * 1000).toLocaleString()
}

export default function Onboarding() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const esRef = useRef(null)

  const refetch = useCallback(async () => {
    try {
      const res = await api.getOnboardingSessions()
      setSessions(res.sessions || [])
    } catch {
      // keep state on transient errors
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])

  useEffect(() => {
    const es = subscribeToEvents({ onOnboarding: () => refetch() })
    esRef.current = es
    return () => es && es.close()
  }, [refetch])

  const restart = async (id) => {
    await api.restartOnboarding(id).catch(() => {})
    await refetch()
  }

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ClipboardList className="w-5 h-5 text-blue-400" />
          <div>
            <h1 className="text-xl font-bold">Onboarding</h1>
            <p className="text-xs text-zinc-500">
              Device enrollment lifecycle — validate → provision → ready
            </p>
          </div>
        </div>
        <button
          onClick={() => { setLoading(true); refetch() }}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-main text-zinc-400 hover:text-zinc-200"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="bg-zinc-900 border border-main rounded-lg px-4 py-10 text-center text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin inline" /> Loading…
        </div>
      ) : sessions.length === 0 ? (
        <div className="bg-zinc-900 border border-main rounded-lg px-4 py-12 text-center text-zinc-500">
          <ClipboardList className="w-6 h-6 mx-auto mb-2 opacity-40" />
          No onboarding sessions — a device starts one when it first registers
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map((s) => {
            const byStep = Object.fromEntries((s.steps || []).map((st) => [st.step, st]))
            return (
              <div key={s.id} className="bg-zinc-900 border border-main rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-3">
                    <Smartphone className="w-4 h-4 text-zinc-400" />
                    <div>
                      <div className="text-sm font-semibold text-zinc-100">{s.device_id}</div>
                      <div className="text-[10px] text-zinc-500 mono">started {fmtTime(s.started_at)}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${STATE_STYLE[s.state] || 'text-zinc-400 border-main'}`}>
                      {s.state}
                    </span>
                    {s.state === 'failed' && (
                      <button
                        onClick={() => restart(s.id)}
                        className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded border border-main text-zinc-300 hover:bg-zinc-800"
                      >
                        <RotateCw className="w-3 h-3" /> Retry
                      </button>
                    )}
                  </div>
                </div>

                {/* Step trail */}
                <div className="flex items-center gap-4">
                  {ORDER.map((step) => {
                    const st = byStep[step]
                    return (
                      <div key={step} className="flex items-center gap-1.5">
                        <StepDot status={st?.status} />
                        <span className={`text-[11px] ${st ? 'text-zinc-300' : 'text-zinc-600'}`}>{step}</span>
                      </div>
                    )
                  })}
                </div>

                {s.error && (
                  <div className="text-[11px] text-red-400 flex items-center gap-1">
                    <XCircle className="w-3.5 h-3.5 shrink-0" /> {s.error}
                  </div>
                )}

                {/* Detail of the latest step */}
                {(s.steps || []).length > 0 && (
                  <div className="text-[10px] text-zinc-500 mono">
                    {s.steps[s.steps.length - 1].detail?.summary ||
                      JSON.stringify(s.steps[s.steps.length - 1].detail)}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
