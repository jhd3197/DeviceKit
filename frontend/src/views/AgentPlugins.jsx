// Agent Plugins view (plan 25 part 5, schema only).
//
// Declare + inspect agent-plugin manifests: capabilities, typed permissions, resource limits
// and a dependency graph. The on-device runtime is deferred, so this surface validates and
// stores the contract and shows the resolved install order — it does not run anything.
import React, { useCallback, useEffect, useState } from 'react'
import {
  Puzzle,
  RefreshCw,
  Loader2,
  Trash2,
  CheckCircle,
  AlertCircle,
  ListOrdered,
} from 'lucide-react'

import { api } from '../api'

const SAMPLE = `{
  "name": "battery-guard",
  "version": "1.0.0",
  "description": "watches battery health",
  "capabilities": {
    "metrics": [{ "name": "battery_health", "unit": "%", "interval_seconds": 60 }],
    "health_checks": [{ "key": "battery_ok", "title": "Battery OK" }]
  },
  "permissions": {
    "filesystem": [{ "path": "/sys/class/power_supply", "mode": "read" }],
    "system": ["battery"]
  },
  "resources": { "max_memory_mb": 64, "max_cpu_percent": 10 },
  "dependencies": []
}`

function Pills({ label, items }) {
  if (!items || items.length === 0) return null
  return (
    <div className="flex items-start gap-2">
      <span className="text-[10px] uppercase font-bold text-zinc-500 mt-0.5 w-20 shrink-0">{label}</span>
      <div className="flex flex-wrap gap-1">
        {items.map((it, i) => (
          <span key={i} className="text-[10px] mono px-1.5 py-0.5 rounded bg-zinc-800 border border-main text-zinc-300">{it}</span>
        ))}
      </div>
    </div>
  )
}

export default function AgentPlugins() {
  const [plugins, setPlugins] = useState([])
  const [order, setOrder] = useState(null)
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState(SAMPLE)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')

  const refetch = useCallback(async () => {
    try {
      const [pl, ord] = await Promise.all([api.getAgentPlugins(), api.getAgentPluginOrder()])
      setPlugins(pl.plugins || [])
      setOrder(ord)
    } catch {
      // keep state
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refetch() }, [refetch])

  const submit = async (validateOnly) => {
    setError(''); setOk(''); setBusy(true)
    let manifest
    try {
      manifest = JSON.parse(draft)
    } catch (e) {
      setError(`JSON parse error: ${e.message}`)
      setBusy(false)
      return
    }
    try {
      if (validateOnly) {
        const res = await api.validateAgentPlugin(manifest)
        if (res.valid) setOk('Manifest is valid')
        else setError(res.errors.join('; '))
      } else {
        const res = await api.declareAgentPlugin(manifest)
        if (res && res.error) setError((res.errors || [res.error]).join('; '))
        else { setOk(`Declared ${res.name} v${res.version}`); await refetch() }
      }
    } catch (e) {
      setError(e.body?.errors?.join('; ') || e.message || 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id) => {
    await api.deleteAgentPlugin(id).catch(() => {})
    await refetch()
  }

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Puzzle className="w-5 h-5 text-purple-400" />
          <div>
            <h1 className="text-xl font-bold">Agent Plugins</h1>
            <p className="text-xs text-zinc-500">
              Declare plugin manifests — capabilities, typed permissions, limits, deps
              <span className="text-amber-400/80"> · runtime deferred (contract only)</span>
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

      {/* Declare form */}
      <div className="border border-main rounded-lg p-4 bg-zinc-900/40 space-y-3">
        <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">Declare a plugin</p>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={12}
          spellCheck={false}
          className="w-full bg-body border border-main rounded px-3 py-2 text-xs mono text-zinc-200 focus:outline-none focus:border-purple-500/50"
        />
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => submit(true)}
            disabled={busy}
            className="text-xs px-3 py-1.5 rounded border border-main text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
          >
            Validate
          </button>
          <button
            onClick={() => submit(false)}
            disabled={busy}
            className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded border border-purple-500/50 bg-purple-500/10 text-purple-300 hover:bg-purple-500/20 disabled:opacity-40"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Puzzle className="w-3.5 h-3.5" />}
            Declare
          </button>
          {error && <span className="flex items-center gap-1 text-xs text-red-400"><AlertCircle className="w-3.5 h-3.5" /> {error}</span>}
          {ok && <span className="flex items-center gap-1 text-xs text-emerald-400"><CheckCircle className="w-3.5 h-3.5" /> {ok}</span>}
        </div>
      </div>

      {/* Resolved install order */}
      {order && (order.order || order.error) && (
        <div className="border border-main rounded-lg p-3 bg-zinc-900/40 flex items-center gap-2 text-xs">
          <ListOrdered className="w-3.5 h-3.5 text-zinc-500" />
          {order.error ? (
            <span className="text-red-400">dependency error: {order.error}</span>
          ) : (
            <span className="text-zinc-400">install order:
              <span className="mono text-zinc-200"> {order.order.join(' → ') || '—'}</span>
            </span>
          )}
        </div>
      )}

      {/* Declared plugins */}
      {loading ? (
        <div className="bg-hover border border-main rounded-lg px-4 py-10 text-center text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin inline" /> Loading…
        </div>
      ) : plugins.length === 0 ? (
        <div className="bg-hover border border-main rounded-lg px-4 py-12 text-center text-zinc-500">
          <Puzzle className="w-6 h-6 mx-auto mb-2 opacity-40" /> No plugins declared
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {plugins.map((p) => {
            const m = p.manifest || {}
            const caps = m.capabilities || {}
            const perms = m.permissions || {}
            return (
              <div key={p.id} className="bg-hover border border-main rounded-lg p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-semibold text-zinc-100">{p.name}</span>
                    <span className="ml-2 text-[11px] mono text-zinc-500">v{p.version}</span>
                  </div>
                  <button onClick={() => remove(p.id)} className="text-zinc-500 hover:text-red-400">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                {m.description && <p className="text-[11px] text-zinc-400">{m.description}</p>}
                <div className="space-y-1 pt-1">
                  <Pills label="metrics" items={(caps.metrics || []).map((x) => x.name)} />
                  <Pills label="commands" items={(caps.commands || []).map((x) => x.name)} />
                  <Pills label="fs" items={(perms.filesystem || []).map((x) => `${x.path}:${x.mode}`)} />
                  <Pills label="system" items={perms.system || []} />
                  <Pills label="deps" items={m.dependencies || []} />
                </div>
                {m.resources && (m.resources.max_memory_mb || m.resources.max_cpu_percent) && (
                  <div className="text-[10px] text-zinc-500 mono pt-1">
                    limits: {m.resources.max_memory_mb ?? '—'} MB · {m.resources.max_cpu_percent ?? '—'}% CPU
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
