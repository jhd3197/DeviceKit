// Agent Updates (OTA) view (plan 25 part 3).
//
// Operator console for rolling a new agent APK to the fleet without touching a phone:
// upload a signed release, open a rollout (canary → staged → full), watch per-device
// progress, and roll back. Backed by /agent-device/ota/*. Refetches on the `ota` SSE event.
import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  Rocket,
  UploadCloud,
  RefreshCw,
  Loader2,
  KeyRound,
  Undo2,
  Pause,
  Play,
  AlertCircle,
  CheckCircle,
  PackageCheck,
} from 'lucide-react'

import { api, subscribeToEvents } from '../api'

const STAGE_STYLE = {
  canary: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
  staged: 'text-blue-400 border-blue-500/40 bg-blue-500/10',
  full: 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10',
}
const STATUS_STYLE = {
  active: 'text-emerald-400',
  completed: 'text-blue-400',
  rolled_back: 'text-red-400',
  paused: 'text-zinc-400',
}

function fmtBytes(n) {
  if (!n) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = n
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(1)} ${u[i]}`
}

// Read a File into a base64 string (strip the data: URL prefix).
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export default function AgentUpdates() {
  const [releases, setReleases] = useState([])
  const [rollouts, setRollouts] = useState([])
  const [pubkey, setPubkey] = useState('')
  const [loading, setLoading] = useState(true)
  const esRef = useRef(null)

  // Upload form
  const [file, setFile] = useState(null)
  const [versionName, setVersionName] = useState('')
  const [versionCode, setVersionCode] = useState('')
  const [notes, setNotes] = useState('')
  const [uploading, setUploading] = useState(false)
  const [formError, setFormError] = useState('')
  const [formOk, setFormOk] = useState('')

  const refetch = useCallback(async () => {
    try {
      const [rel, rol] = await Promise.all([api.getOtaReleases(), api.getOtaRollouts()])
      setReleases(rel.releases || [])
      setRollouts(rol.rollouts || [])
    } catch {
      // keep state on transient errors
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refetch()
    api.getOtaPubkey().then((r) => setPubkey(r.public_key || '')).catch(() => {})
  }, [refetch])

  useEffect(() => {
    const es = subscribeToEvents({ onOta: () => refetch() })
    esRef.current = es
    return () => es && es.close()
  }, [refetch])

  const submitUpload = async (e) => {
    e.preventDefault()
    setFormError('')
    setFormOk('')
    if (!file || !versionName.trim() || !versionCode) {
      setFormError('APK file, version name and version code are required')
      return
    }
    setUploading(true)
    try {
      const apk_b64 = await fileToBase64(file)
      const rel = await api.createOtaRelease({
        apk_b64,
        version_name: versionName.trim(),
        version_code: Number(versionCode),
        notes: notes.trim() || undefined,
        filename: file.name,
      })
      if (rel && rel.error) {
        setFormError(rel.error)
      } else {
        setFormOk(`Published ${rel.version_name} (code ${rel.version_code})`)
        setFile(null); setVersionName(''); setVersionCode(''); setNotes('')
        await refetch()
      }
    } catch (err) {
      setFormError(err.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const startRollout = async (releaseId) => {
    try {
      await api.createOtaRollout({ release_id: releaseId, target_kind: 'all' })
      await refetch()
    } catch (err) {
      setFormError(err.message || 'Rollout failed')
    }
  }

  const rollback = async (id) => {
    await api.rollbackOtaRollout(id, 'operator rollback').catch(() => {})
    await refetch()
  }

  const togglePause = async (r) => {
    await api.pauseOtaRollout(r.id, r.status !== 'paused').catch(() => {})
    await refetch()
  }

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Rocket className="w-5 h-5 text-emerald-400" />
          <div>
            <h1 className="text-xl font-bold">Agent Updates</h1>
            <p className="text-xs text-zinc-500">
              Sign, publish and roll out agent APKs over the air (canary → staged → full)
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

      {pubkey && (
        <div className="border border-main rounded-lg p-3 bg-zinc-900/40 flex items-start gap-2">
          <KeyRound className="w-3.5 h-3.5 text-zinc-500 mt-0.5 shrink-0" />
          <div className="min-w-0">
            <div className="text-[10px] uppercase font-bold text-zinc-500">Signing public key (pin this in the agent)</div>
            <div className="text-[11px] mono text-zinc-400 break-all">{pubkey}</div>
          </div>
        </div>
      )}

      {/* Upload a release */}
      <div className="border border-main rounded-lg p-4 bg-zinc-900/40 space-y-3">
        <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 flex items-center gap-2">
          <UploadCloud className="w-3.5 h-3.5" /> Publish a release
        </p>
        <form onSubmit={submitUpload} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 font-bold mb-1">APK file</label>
            <input
              type="file"
              accept=".apk"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="text-xs text-zinc-400 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border file:border-main file:bg-zinc-800 file:text-zinc-200 file:text-xs"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 font-bold mb-1">Version name</label>
            <input
              value={versionName}
              onChange={(e) => setVersionName(e.target.value)}
              placeholder="1.3.0"
              className="w-28 bg-body border border-main rounded px-3 py-2 text-sm mono text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-emerald-500/50"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 font-bold mb-1">Version code</label>
            <input
              type="number"
              value={versionCode}
              onChange={(e) => setVersionCode(e.target.value)}
              placeholder="7"
              className="w-24 bg-body border border-main rounded px-3 py-2 text-sm mono text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-emerald-500/50"
            />
          </div>
          <button
            type="submit"
            disabled={uploading}
            className="flex items-center gap-1.5 text-xs px-4 py-2 rounded border border-emerald-500/50 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-40"
          >
            {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UploadCloud className="w-3.5 h-3.5" />}
            Publish
          </button>
          {formError && (
            <span className="flex items-center gap-1 text-xs text-red-400">
              <AlertCircle className="w-3.5 h-3.5" /> {formError}
            </span>
          )}
          {formOk && (
            <span className="flex items-center gap-1 text-xs text-emerald-400">
              <CheckCircle className="w-3.5 h-3.5" /> {formOk}
            </span>
          )}
        </form>
      </div>

      {loading ? (
        <div className="bg-hover border border-main rounded-lg px-4 py-10 text-center text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin inline" /> Loading…
        </div>
      ) : (
        <>
          {/* Active + historical rollouts */}
          <div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 mb-3">Rollouts</p>
            {rollouts.length === 0 ? (
              <div className="bg-hover border border-main rounded-lg px-4 py-8 text-center text-zinc-500">
                No rollouts yet — publish a release and roll it out
              </div>
            ) : (
              <div className="space-y-3">
                {rollouts.map((r) => {
                  const p = r.progress || {}
                  const rel = releases.find((x) => x.id === r.release_id)
                  return (
                    <div key={r.id} className="bg-hover border border-main rounded-lg p-4 space-y-3">
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <div className="flex items-center gap-3">
                          <PackageCheck className="w-4 h-4 text-zinc-400" />
                          <div>
                            <div className="text-sm font-semibold text-zinc-100">
                              {rel ? `${rel.version_name} (code ${rel.version_code})` : r.release_id}
                              {r.rollback_of && <span className="ml-2 text-[10px] text-red-400">rollback</span>}
                            </div>
                            <div className="text-[10px] text-zinc-500 mono">{r.id}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${STAGE_STYLE[r.stage] || 'text-zinc-400 border-main'}`}>
                            {r.stage}
                          </span>
                          <span className={`text-[10px] uppercase font-bold ${STATUS_STYLE[r.status] || 'text-zinc-400'}`}>
                            {r.status}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-4 text-[11px] text-zinc-400">
                        <span className="text-emerald-400">{p.installed || 0} installed</span>
                        <span className="text-amber-400">{p.offered || 0} offered</span>
                        <span className="text-red-400">{p.failed || 0} failed</span>
                        <span className="text-zinc-500">{p.total || 0} total</span>
                      </div>

                      {r.status === 'active' || r.status === 'paused' ? (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => togglePause(r)}
                            className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded border border-main text-zinc-300 hover:bg-zinc-800"
                          >
                            {r.status === 'paused'
                              ? <><Play className="w-3 h-3" /> Resume</>
                              : <><Pause className="w-3 h-3" /> Pause</>}
                          </button>
                          <button
                            onClick={() => rollback(r.id)}
                            className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded border border-red-500/40 text-red-400 hover:bg-red-500/10"
                          >
                            <Undo2 className="w-3 h-3" /> Roll back
                          </button>
                        </div>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Releases */}
          <div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 mb-3">Releases</p>
            <div className="bg-hover border border-main rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-[10px] uppercase text-zinc-500 border-b border-main">
                      <th className="text-left font-bold px-4 py-2">Version</th>
                      <th className="text-left font-bold px-4 py-2">Code</th>
                      <th className="text-left font-bold px-4 py-2">Size</th>
                      <th className="text-left font-bold px-4 py-2">SHA-256</th>
                      <th className="text-left font-bold px-4 py-2">Status</th>
                      <th className="text-right font-bold px-4 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {releases.length === 0 ? (
                      <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-500">No releases published</td></tr>
                    ) : releases.map((rel) => (
                      <tr key={rel.id} className="border-b border-main/50 hover:bg-zinc-800/40">
                        <td className="px-4 py-2 mono text-emerald-300">{rel.version_name}</td>
                        <td className="px-4 py-2 mono text-zinc-400">{rel.version_code}</td>
                        <td className="px-4 py-2 mono text-zinc-400">{fmtBytes(rel.size_bytes)}</td>
                        <td className="px-4 py-2 mono text-zinc-500 truncate max-w-[160px]" title={rel.sha256}>{rel.sha256?.slice(0, 16)}…</td>
                        <td className="px-4 py-2">
                          <span className={rel.status === 'published' ? 'text-emerald-400' : 'text-red-400'}>{rel.status}</span>
                        </td>
                        <td className="px-4 py-2 text-right">
                          {rel.status === 'published' && (
                            <button
                              onClick={() => startRollout(rel.id)}
                              className="text-[11px] px-2.5 py-1 rounded border border-emerald-500/50 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                            >
                              Roll out
                            </button>
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
