import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus,
  Play,
  Pencil,
  Trash2,
  X,
  Clock,
  CheckCircle,
  XCircle,
  Loader,
} from 'lucide-react'
import { api } from '../api'

export default function Automations() {
  const navigate = useNavigate()
  const [automations, setAutomations] = useState([])
  const [runs, setRuns] = useState([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)

  // Run dialog state
  const [runDialog, setRunDialog] = useState(null) // automation object or null
  const [devices, setDevices] = useState([])
  const [selectedDevice, setSelectedDevice] = useState('')
  const [launching, setLaunching] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const [autoRes, runsRes] = await Promise.all([
        api.getAutomations(),
        api.getAutomationRuns({ limit: 20 }),
      ])
      setAutomations(autoRes.automations || [])
      setRuns(runsRes.runs || [])
    } catch (e) {
      console.error('Failed to fetch automations:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleDelete = async (id) => {
    try {
      await api.deleteAutomation(id)
      setAutomations((prev) => prev.filter((a) => a.id !== id))
    } catch (e) {
      console.error('Failed to delete:', e)
    }
  }

  const openRunDialog = async (automation) => {
    setRunDialog(automation)
    setSelectedDevice('')
    try {
      const res = await api.getDevices()
      setDevices(res.devices || [])
      if (res.devices?.length > 0) {
        setSelectedDevice(res.devices[0].device_id)
      }
    } catch {
      setDevices([])
    }
  }

  const handleRun = async () => {
    if (!selectedDevice || !runDialog) return
    setLaunching(true)
    try {
      const run = await api.runAutomation(runDialog.id, selectedDevice)
      setRunDialog(null)
      navigate(`/automations/runs/${run.id}`)
    } catch (e) {
      console.error('Failed to run automation:', e)
    } finally {
      setLaunching(false)
    }
  }

  const filtered = automations.filter(
    (a) =>
      a.name?.toLowerCase().includes(filter.toLowerCase()) ||
      (a.tags || []).some((t) => t.toLowerCase().includes(filter.toLowerCase()))
  )

  const statusBadge = (status) => {
    const map = {
      completed: 'bg-emerald-500/10 text-emerald-400',
      failed: 'bg-red-500/10 text-red-400',
      running: 'bg-blue-500/10 text-blue-400',
      cancelled: 'bg-zinc-500/10 text-zinc-400',
    }
    return (
      <span
        className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${map[status] || map.cancelled}`}
      >
        {status}
      </span>
    )
  }

  return (
    <>
      {/* Header */}
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-black shrink-0">
        <h2 className="text-sm font-bold uppercase tracking-widest text-zinc-400">
          Automations
        </h2>
        <button
          onClick={() => navigate('/automations/new')}
          className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2"
        >
          <Plus className="w-3 h-3" /> New Automation
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Filter */}
        <input
          type="text"
          placeholder="Filter by name or tag..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full max-w-md bg-black border border-main px-3 py-1.5 text-xs rounded focus:outline-none"
        />

        {/* Automations table */}
        <div className="bg-card border border-main rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-main text-[10px] text-zinc-500 uppercase">
                <th className="text-left px-4 py-3 font-bold">Name</th>
                <th className="text-left px-4 py-3 font-bold">Steps</th>
                <th className="text-left px-4 py-3 font-bold">Tags</th>
                <th className="text-left px-4 py-3 font-bold">Updated</th>
                <th className="text-right px-4 py-3 font-bold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-zinc-600">
                    Loading...
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-zinc-600">
                    {automations.length === 0
                      ? 'No automations yet. Create one to get started.'
                      : 'No automations match your filter.'}
                  </td>
                </tr>
              ) : (
                filtered.map((a) => (
                  <tr
                    key={a.id}
                    className="border-b border-main hover:bg-zinc-900/20 transition-colors"
                  >
                    <td className="px-4 py-3 font-medium">{a.name}</td>
                    <td className="px-4 py-3 mono text-zinc-400">
                      {(a.steps || []).length}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 flex-wrap">
                        {(a.tags || []).map((tag) => (
                          <span
                            key={tag}
                            className="bg-zinc-800 text-zinc-400 text-[10px] px-1.5 py-0.5 rounded"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-zinc-500 mono text-[10px]">
                      {a.updated_at ? timeAgo(Number(a.updated_at)) : '--'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => navigate(`/automations/${a.id}/edit`)}
                          className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-white transition-colors"
                          title="Edit"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => openRunDialog(a)}
                          className="p-1.5 rounded hover:bg-zinc-800 text-emerald-500 hover:text-emerald-400 transition-colors"
                          title="Run"
                        >
                          <Play className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleDelete(a.id)}
                          className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-red-400 transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Recent runs */}
        <div>
          <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-3">
            Recent Runs
          </h3>
          <div className="bg-card border border-main rounded overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-main text-[10px] text-zinc-500 uppercase">
                  <th className="text-left px-4 py-3 font-bold">Automation</th>
                  <th className="text-left px-4 py-3 font-bold">Device</th>
                  <th className="text-left px-4 py-3 font-bold">Status</th>
                  <th className="text-left px-4 py-3 font-bold">Duration</th>
                  <th className="text-right px-4 py-3 font-bold" />
                </tr>
              </thead>
              <tbody>
                {runs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-6 text-center text-zinc-600">
                      No runs yet.
                    </td>
                  </tr>
                ) : (
                  runs.map((r) => (
                    <tr
                      key={r.id}
                      className="border-b border-main hover:bg-zinc-900/20 transition-colors cursor-pointer"
                      onClick={() => navigate(`/automations/runs/${r.id}`)}
                    >
                      <td className="px-4 py-3 font-medium">
                        {r.automation_name || r.automation_id}
                      </td>
                      <td className="px-4 py-3 mono text-zinc-400 text-[10px]">
                        {r.device_id}
                      </td>
                      <td className="px-4 py-3">{statusBadge(r.status)}</td>
                      <td className="px-4 py-3 mono text-zinc-500 text-[10px]">
                        {r.finished_at && r.started_at
                          ? `${((Number(r.finished_at) - Number(r.started_at)) * 1000).toFixed(0)}ms`
                          : r.status === 'running'
                            ? 'In progress'
                            : '--'}
                      </td>
                      <td className="px-4 py-3 text-right text-zinc-500">
                        {r.status === 'running' && (
                          <Loader className="w-3 h-3 animate-spin inline" />
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Run dialog overlay */}
      {runDialog && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-card border border-main rounded-lg w-full max-w-sm p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-sm font-bold">Run Automation</h3>
              <button
                onClick={() => setRunDialog(null)}
                className="text-zinc-500 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-zinc-400 mb-4">
              <span className="text-white font-medium">{runDialog.name}</span>{' '}
              &mdash; {(runDialog.steps || []).length} steps
            </p>
            <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
              Target Device
            </label>
            {devices.length === 0 ? (
              <p className="text-xs text-zinc-500 mb-4">No devices connected.</p>
            ) : (
              <select
                value={selectedDevice}
                onChange={(e) => setSelectedDevice(e.target.value)}
                className="w-full bg-black border border-main px-3 py-2 text-xs rounded mb-4 focus:outline-none"
              >
                {devices.map((d) => (
                  <option key={d.device_id} value={d.device_id}>
                    {d.name || d.device_id} ({d.device_id})
                  </option>
                ))}
              </select>
            )}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setRunDialog(null)}
                className="px-4 py-1.5 text-xs rounded border border-main text-zinc-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleRun}
                disabled={!selectedDevice || launching}
                className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2"
              >
                {launching ? (
                  <Loader className="w-3 h-3 animate-spin" />
                ) : (
                  <Play className="w-3 h-3 fill-current" />
                )}
                Execute
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function timeAgo(ts) {
  if (!ts) return ''
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}
