// Agent Versions view (plan 25 part 2).
//
// "Which agent version is on which device" — the read side of OTA targeting. Lists a
// version → devices rollup (GET /agent-device/versions) and a per-device table. Refetches
// on the `device_connected` / `device_state` SSE events so the picture stays live. The
// roll-forward/back actions land with OTA (phase 3); this view answers "where are we now".
import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  GitBranch,
  Smartphone,
  RefreshCw,
  Loader2,
  CircleDot,
  CircleOff,
  Layers,
} from 'lucide-react'

import { api, subscribeToEvents } from '../api'

export default function FleetVersions() {
  const [data, setData] = useState({ devices: [], versions: [], distinct_versions: 0 })
  const [loading, setLoading] = useState(true)
  const esRef = useRef(null)

  const fetchVersions = useCallback(async () => {
    try {
      const res = await api.getAgentVersions()
      setData(res || { devices: [], versions: [], distinct_versions: 0 })
    } catch {
      // keep current state on transient errors
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchVersions()
  }, [fetchVersions])

  // Live: any connect/disconnect/state change can shift the version picture.
  useEffect(() => {
    const es = subscribeToEvents({
      onDeviceConnected: () => fetchVersions(),
      onDeviceDisconnected: () => fetchVersions(),
      onDeviceState: () => fetchVersions(),
    })
    esRef.current = es
    return () => es && es.close()
  }, [fetchVersions])

  const { devices, versions, distinct_versions } = data

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <GitBranch className="w-5 h-5 text-blue-400" />
          <div>
            <h1 className="text-xl font-bold">Agent Versions</h1>
            <p className="text-xs text-zinc-500">
              Which agent version is running on which device
            </p>
          </div>
        </div>
        <button
          onClick={() => { setLoading(true); fetchVersions() }}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-main text-zinc-400 hover:text-zinc-200"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Version rollup */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-zinc-900 border border-main rounded-lg p-3">
          <div className="text-[10px] uppercase font-bold text-zinc-500">Devices</div>
          <div className="text-2xl font-bold mono">{devices.length}</div>
        </div>
        <div className="bg-zinc-900 border border-main rounded-lg p-3">
          <div className="text-[10px] uppercase font-bold text-zinc-500">Versions</div>
          <div className="text-2xl font-bold mono">{distinct_versions}</div>
        </div>
      </div>

      {loading ? (
        <div className="bg-zinc-900 border border-main rounded-lg px-4 py-10 text-center text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin inline" /> Loading…
        </div>
      ) : (
        <>
          {/* Per-version breakdown */}
          <div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 mb-3 flex items-center gap-2">
              <Layers className="w-3.5 h-3.5" /> By version
            </p>
            {versions.length === 0 ? (
              <div className="bg-zinc-900 border border-main rounded-lg px-4 py-12 text-center text-zinc-500">
                No agent devices registered
              </div>
            ) : (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {versions.map((v) => (
                  <div key={v.version} className="bg-zinc-900 border border-main rounded-lg p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="mono text-sm font-semibold text-blue-300">{v.version}</span>
                      <span className="text-[10px] text-zinc-500">
                        {v.online}/{v.count} online
                      </span>
                    </div>
                    <div className="text-[11px] text-zinc-500">
                      {v.count} device{v.count === 1 ? '' : 's'}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Per-device table */}
          <div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 mb-3">
              Devices
            </p>
            <div className="bg-zinc-900 border border-main rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-[10px] uppercase text-zinc-500 border-b border-main">
                      <th className="text-left font-bold px-4 py-2">Device</th>
                      <th className="text-left font-bold px-4 py-2">Version</th>
                      <th className="text-left font-bold px-4 py-2">Code</th>
                      <th className="text-left font-bold px-4 py-2">API</th>
                      <th className="text-left font-bold px-4 py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {devices.map((d) => (
                      <tr key={d.device_id} className="border-b border-main/50 hover:bg-zinc-800/40">
                        <td className="px-4 py-2">
                          <div className="flex items-center gap-2">
                            <Smartphone className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
                            <div className="min-w-0">
                              <div className="text-zinc-200 truncate">{d.model || d.device_id}</div>
                              <div className="text-[10px] text-zinc-500 mono truncate">{d.device_id}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-2 mono text-blue-300">{d.agent_version || '—'}</td>
                        <td className="px-4 py-2 mono text-zinc-400">{d.agent_version_code ?? '—'}</td>
                        <td className="px-4 py-2 mono text-zinc-400">{d.android_api ?? '—'}</td>
                        <td className="px-4 py-2">
                          {d.online ? (
                            <span className="flex items-center gap-1 text-emerald-400">
                              <CircleDot className="w-3 h-3" /> online
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-zinc-500">
                              <CircleOff className="w-3 h-3" /> offline
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
