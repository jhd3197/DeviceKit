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
  Upload,
  Timer,
  Pause,
  Lightbulb,
  HeartPulse,
} from 'lucide-react'
import { api } from '../api'

export default function Automations() {
  const navigate = useNavigate()
  const [automations, setAutomations] = useState([])
  const [runs, setRuns] = useState([])
  const [schedules, setSchedules] = useState([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)

  // Run dialog state
  const [runDialog, setRunDialog] = useState(null) // automation object or null
  const [devices, setDevices] = useState([])
  const [selectedDevice, setSelectedDevice] = useState('')
  const [launching, setLaunching] = useState(false)
  const [selfHeal, setSelfHeal] = useState(false)

  // Schedule dialog state
  const [scheduleDialog, setScheduleDialog] = useState(null) // automation object or null
  const [schedDevices, setSchedDevices] = useState([])
  const [schedDevice, setSchedDevice] = useState('')
  const [schedInterval, setSchedInterval] = useState(60)
  const [creatingSched, setCreatingSched] = useState(false)

  // Explain modal
  const [explainModal, setExplainModal] = useState(null) // { automationId, name }
  const [explanation, setExplanation] = useState('')
  const [explaining, setExplaining] = useState(false)

  // Import
  const importRef = React.useRef(null)

  const fetchData = useCallback(async () => {
    try {
      const [autoRes, runsRes, schedRes] = await Promise.all([
        api.getAutomations(),
        api.getAutomationRuns({ limit: 20 }),
        api.getSchedules(),
      ])
      setAutomations(autoRes.automations || [])
      setRuns(runsRes.runs || [])
      setSchedules(schedRes.schedules || [])
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
    setSelfHeal(false)
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
      const run = await api.runAutomation(runDialog.id, selectedDevice, selfHeal)
      setRunDialog(null)
      navigate(`/automations/runs/${run.id}`)
    } catch (e) {
      console.error('Failed to run automation:', e)
    } finally {
      setLaunching(false)
    }
  }

  const openScheduleDialog = async (automation) => {
    setScheduleDialog(automation)
    setSchedDevice('')
    setSchedInterval(60)
    try {
      const res = await api.getDevices()
      setSchedDevices(res.devices || [])
      if (res.devices?.length > 0) setSchedDevice(res.devices[0].device_id)
    } catch {
      setSchedDevices([])
    }
  }

  const handleCreateSchedule = async () => {
    if (!schedDevice || !scheduleDialog) return
    setCreatingSched(true)
    try {
      await api.createSchedule({
        automation_id: scheduleDialog.id,
        device_id: schedDevice,
        interval_minutes: Number(schedInterval),
      })
      setScheduleDialog(null)
      fetchData()
    } catch (e) {
      console.error('Failed to create schedule:', e)
    } finally {
      setCreatingSched(false)
    }
  }

  const handleToggleSchedule = async (sched) => {
    try {
      await api.updateSchedule(sched.id, { enabled: !sched.enabled })
      fetchData()
    } catch (e) {
      console.error('Failed to toggle schedule:', e)
    }
  }

  const handleDeleteSchedule = async (id) => {
    try {
      await api.deleteSchedule(id)
      setSchedules((prev) => prev.filter((s) => s.id !== id))
    } catch (e) {
      console.error('Failed to delete schedule:', e)
    }
  }

  const handleImport = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const automation = await api.importAutomation(data)
      navigate(`/automations/${automation.id}/edit`)
    } catch (err) {
      console.error('Failed to import:', err)
    }
    e.target.value = ''
  }

  const handleExplain = async (automation) => {
    setExplainModal({ automationId: automation.id, name: automation.name })
    setExplanation('')
    setExplaining(true)
    try {
      const result = await api.explainAutomation(automation.id)
      setExplanation(result.explanation || result.error || 'No explanation available.')
    } catch (e) {
      setExplanation(`Failed: ${e.message}`)
    } finally {
      setExplaining(false)
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
        <div className="flex items-center gap-2">
          <input
            ref={importRef}
            type="file"
            accept=".json"
            className="hidden"
            onChange={handleImport}
          />
          <button
            onClick={() => importRef.current?.click()}
            className="border border-main text-zinc-400 hover:text-white text-xs font-bold px-3 py-1.5 rounded transition-colors flex items-center gap-2"
          >
            <Upload className="w-3 h-3" /> Import
          </button>
          <button
            onClick={() => navigate('/automations/new')}
            className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2"
          >
            <Plus className="w-3 h-3" /> New Automation
          </button>
        </div>
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
                          onClick={() => handleExplain(a)}
                          className="p-1.5 rounded hover:bg-zinc-800 text-amber-500 hover:text-amber-400 transition-colors"
                          title="Explain"
                        >
                          <Lightbulb className="w-3.5 h-3.5" />
                        </button>
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
                          onClick={() => openScheduleDialog(a)}
                          className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-blue-400 transition-colors"
                          title="Schedule"
                        >
                          <Timer className="w-3.5 h-3.5" />
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
        {/* Schedules */}
        {schedules.length > 0 && (
          <div>
            <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-3">
              Schedules
            </h3>
            <div className="bg-card border border-main rounded overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-main text-[10px] text-zinc-500 uppercase">
                    <th className="text-left px-4 py-3 font-bold">Automation</th>
                    <th className="text-left px-4 py-3 font-bold">Device</th>
                    <th className="text-left px-4 py-3 font-bold">Interval</th>
                    <th className="text-left px-4 py-3 font-bold">Next Run</th>
                    <th className="text-left px-4 py-3 font-bold">Status</th>
                    <th className="text-right px-4 py-3 font-bold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {schedules.map((s) => (
                    <tr key={s.id} className="border-b border-main hover:bg-zinc-900/20 transition-colors">
                      <td className="px-4 py-3 font-medium">{s.automation_name}</td>
                      <td className="px-4 py-3 mono text-zinc-400 text-[10px]">{s.device_id}</td>
                      <td className="px-4 py-3 mono text-zinc-400">{s.interval_minutes}m</td>
                      <td className="px-4 py-3 mono text-zinc-500 text-[10px]">
                        {s.next_run_at ? new Date(s.next_run_at * 1000).toLocaleTimeString() : '--'}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                          s.enabled
                            ? 'bg-emerald-500/10 text-emerald-400'
                            : 'bg-zinc-500/10 text-zinc-400'
                        }`}>
                          {s.enabled ? 'Active' : 'Paused'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-1">
                          <button
                            onClick={() => handleToggleSchedule(s)}
                            className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-white transition-colors"
                            title={s.enabled ? 'Pause' : 'Resume'}
                          >
                            {s.enabled ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                          </button>
                          <button
                            onClick={() => handleDeleteSchedule(s.id)}
                            className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-red-400 transition-colors"
                            title="Delete schedule"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
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

            {/* Self-heal toggle */}
            <label className="flex items-center gap-2 mb-4 cursor-pointer group">
              <input
                type="checkbox"
                checked={selfHeal}
                onChange={(e) => setSelfHeal(e.target.checked)}
                className="rounded border-zinc-600 bg-black text-amber-500 focus:ring-amber-500 focus:ring-offset-0"
              />
              <span className="text-xs text-zinc-400 group-hover:text-zinc-300 transition-colors flex items-center gap-1.5">
                <HeartPulse className="w-3 h-3 text-amber-500" />
                Enable self-healing
              </span>
              <span className="text-[10px] text-zinc-600" title="When a UI step fails, AI will attempt to find the correct element and retry">
                (?)
              </span>
            </label>

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

      {/* Schedule dialog overlay */}
      {scheduleDialog && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-card border border-main rounded-lg w-full max-w-sm p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-sm font-bold">Schedule Automation</h3>
              <button
                onClick={() => setScheduleDialog(null)}
                className="text-zinc-500 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-zinc-400 mb-4">
              <span className="text-white font-medium">{scheduleDialog.name}</span>
            </p>
            <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
              Target Device
            </label>
            {schedDevices.length === 0 ? (
              <p className="text-xs text-zinc-500 mb-4">No devices connected.</p>
            ) : (
              <select
                value={schedDevice}
                onChange={(e) => setSchedDevice(e.target.value)}
                className="w-full bg-black border border-main px-3 py-2 text-xs rounded mb-4 focus:outline-none"
              >
                {schedDevices.map((d) => (
                  <option key={d.device_id} value={d.device_id}>
                    {d.name || d.device_id} ({d.device_id})
                  </option>
                ))}
              </select>
            )}
            <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
              Interval (minutes)
            </label>
            <input
              type="number"
              min={1}
              value={schedInterval}
              onChange={(e) => setSchedInterval(e.target.value)}
              className="w-full bg-black border border-main px-3 py-2 text-xs rounded mb-4 focus:outline-none"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setScheduleDialog(null)}
                className="px-4 py-1.5 text-xs rounded border border-main text-zinc-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateSchedule}
                disabled={!schedDevice || creatingSched}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2"
              >
                {creatingSched ? (
                  <Loader className="w-3 h-3 animate-spin" />
                ) : (
                  <Timer className="w-3 h-3" />
                )}
                Create Schedule
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Explain modal */}
      {explainModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-card border border-main rounded-lg w-full max-w-lg p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-sm font-bold flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-amber-400" />
                Explain: {explainModal.name}
              </h3>
              <button
                onClick={() => setExplainModal(null)}
                className="text-zinc-500 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {explaining ? (
              <div className="flex items-center gap-2 py-8 justify-center text-zinc-500 text-xs">
                <Loader className="w-4 h-4 animate-spin" /> Generating explanation...
              </div>
            ) : (
              <div className="text-xs text-zinc-300 whitespace-pre-wrap leading-relaxed max-h-[60vh] overflow-y-auto">
                {explanation}
              </div>
            )}
            <div className="flex justify-end mt-4">
              <button
                onClick={() => setExplainModal(null)}
                className="px-4 py-1.5 text-xs rounded border border-main text-zinc-400 hover:text-white transition-colors"
              >
                Close
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
