import React, { useState, useEffect, useCallback } from 'react'
import {
  Plus,
  Pencil,
  Trash2,
  X,
  Play,
  Loader,
  CheckCircle,
  XCircle,
} from 'lucide-react'
import { api } from '../api'

const PRESET_COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#6b7280']

export default function FleetGroups() {
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [devices, setDevices] = useState([])

  // Create/Edit dialog
  const [editDialog, setEditDialog] = useState(null) // null | { mode: 'create'|'edit', group }
  const [formName, setFormName] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formColor, setFormColor] = useState(PRESET_COLORS[0])
  const [formTags, setFormTags] = useState('')
  const [formDeviceIds, setFormDeviceIds] = useState([])
  const [saving, setSaving] = useState(false)

  // Bulk action dialog
  const [bulkDialog, setBulkDialog] = useState(null) // group or null
  const [bulkAction, setBulkAction] = useState('command')
  const [bulkCommand, setBulkCommand] = useState('')
  const [bulkRunning, setBulkRunning] = useState(false)
  const [bulkResults, setBulkResults] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      const [gRes, dRes] = await Promise.all([
        api.getFleetGroups(),
        api.getDevices(),
      ])
      setGroups(gRes.groups || [])
      setDevices(dRes.devices || [])
    } catch (e) {
      console.error('Failed to fetch fleet data:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const filtered = groups.filter(
    (g) =>
      g.name?.toLowerCase().includes(filter.toLowerCase()) ||
      (g.tags || []).some((t) => t.toLowerCase().includes(filter.toLowerCase()))
  )

  // ── Create / Edit ───────────────────────────────────────

  const openCreate = () => {
    setEditDialog({ mode: 'create' })
    setFormName('')
    setFormDesc('')
    setFormColor(PRESET_COLORS[0])
    setFormTags('')
    setFormDeviceIds([])
  }

  const openEdit = (group) => {
    setEditDialog({ mode: 'edit', group })
    setFormName(group.name)
    setFormDesc(group.description || '')
    setFormColor(group.color || PRESET_COLORS[0])
    setFormTags((group.tags || []).join(', '))
    setFormDeviceIds([...(group.device_ids || [])])
  }

  const handleSave = async () => {
    setSaving(true)
    const tags = formTags.split(',').map((t) => t.trim()).filter(Boolean)
    const payload = {
      name: formName,
      description: formDesc,
      color: formColor,
      tags,
      device_ids: formDeviceIds,
    }
    try {
      if (editDialog.mode === 'create') {
        await api.createFleetGroup(payload)
      } else {
        await api.updateFleetGroup(editDialog.group.id, payload)
      }
      setEditDialog(null)
      fetchData()
    } catch (e) {
      console.error('Save failed:', e)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    try {
      await api.deleteFleetGroup(id)
      setGroups((prev) => prev.filter((g) => g.id !== id))
    } catch (e) {
      console.error('Delete failed:', e)
    }
  }

  const toggleDevice = (did) => {
    setFormDeviceIds((prev) =>
      prev.includes(did) ? prev.filter((d) => d !== did) : [...prev, did]
    )
  }

  // ── Bulk actions ────────────────────────────────────────

  const openBulk = (group) => {
    setBulkDialog(group)
    setBulkAction('command')
    setBulkCommand('')
    setBulkResults(null)
  }

  const executeBulk = async () => {
    if (!bulkDialog) return
    setBulkRunning(true)
    setBulkResults(null)
    try {
      let res
      if (bulkAction === 'command') {
        res = await api.bulkCommand(bulkDialog.id, bulkCommand)
      } else if (bulkAction === 'install') {
        res = await api.bulkInstall(bulkDialog.id)
      } else {
        res = await api.bulkReboot(bulkDialog.id)
      }
      setBulkResults(res.results || [])
    } catch (e) {
      console.error('Bulk action failed:', e)
    } finally {
      setBulkRunning(false)
    }
  }

  return (
    <>
      {/* Header */}
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-body shrink-0">
        <h2 className="text-sm font-bold uppercase tracking-widest text-zinc-400">
          Device Groups
        </h2>
        <button
          onClick={openCreate}
          className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2"
        >
          <Plus className="w-3 h-3" /> New Group
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Filter */}
        <input
          type="text"
          placeholder="Filter by name or tag..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full max-w-md bg-body border border-main px-3 py-1.5 text-xs rounded focus:outline-none"
        />

        {/* Groups table */}
        <div className="bg-card border border-main rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-main text-[10px] text-zinc-500 uppercase">
                <th className="text-left px-4 py-3 font-bold">Name</th>
                <th className="text-left px-4 py-3 font-bold">Description</th>
                <th className="text-left px-4 py-3 font-bold">Tags</th>
                <th className="text-left px-4 py-3 font-bold">Devices</th>
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
                    {groups.length === 0
                      ? 'No device groups yet. Create one to get started.'
                      : 'No groups match your filter.'}
                  </td>
                </tr>
              ) : (
                filtered.map((g) => (
                  <tr
                    key={g.id}
                    className="border-b border-main hover:bg-zinc-900/20 transition-colors"
                  >
                    <td className="px-4 py-3 font-medium">
                      <span className="flex items-center gap-2">
                        <span
                          className="w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: g.color || '#10b981' }}
                        />
                        {g.name}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-zinc-400 truncate max-w-[200px]">
                      {g.description || '--'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 flex-wrap">
                        {(g.tags || []).map((tag) => (
                          <span
                            key={tag}
                            className="bg-zinc-800 text-zinc-400 text-[10px] px-1.5 py-0.5 rounded"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 mono text-zinc-400">
                      {(g.device_ids || []).length}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => openEdit(g)}
                          className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-strong transition-colors"
                          title="Edit"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => openBulk(g)}
                          className="p-1.5 rounded hover:bg-zinc-800 text-emerald-500 hover:text-emerald-400 transition-colors"
                          title="Bulk Action"
                        >
                          <Play className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleDelete(g.id)}
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
      </div>

      {/* Create / Edit dialog */}
      {editDialog && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-card border border-main rounded-lg w-full max-w-md p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-sm font-bold">
                {editDialog.mode === 'create' ? 'Create Group' : 'Edit Group'}
              </h3>
              <button
                onClick={() => setEditDialog(null)}
                className="text-zinc-500 hover:text-strong transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
                  Name
                </label>
                <input
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full bg-body border border-main px-3 py-2 text-xs rounded focus:outline-none"
                  placeholder="Group name..."
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
                  Description
                </label>
                <textarea
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  className="w-full bg-body border border-main px-3 py-2 text-xs rounded focus:outline-none resize-none h-16"
                  placeholder="Optional description..."
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
                  Color
                </label>
                <div className="flex gap-2">
                  {PRESET_COLORS.map((c) => (
                    <button
                      key={c}
                      onClick={() => setFormColor(c)}
                      className={`w-7 h-7 rounded-full border-2 transition-all ${
                        formColor === c ? 'border-white scale-110' : 'border-transparent'
                      }`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
                  Tags (comma-separated)
                </label>
                <input
                  value={formTags}
                  onChange={(e) => setFormTags(e.target.value)}
                  className="w-full bg-body border border-main px-3 py-2 text-xs rounded focus:outline-none"
                  placeholder="production, qa, staging..."
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
                  Devices
                </label>
                <div className="max-h-40 overflow-y-auto bg-body border border-main rounded p-2 space-y-1">
                  {devices.length === 0 ? (
                    <p className="text-[10px] text-zinc-600 p-1">No devices available</p>
                  ) : (
                    devices.map((d) => (
                      <label
                        key={d.device_id}
                        className="flex items-center gap-2 px-2 py-1 rounded hover:bg-hover cursor-pointer text-xs"
                      >
                        <input
                          type="checkbox"
                          checked={formDeviceIds.includes(d.device_id)}
                          onChange={() => toggleDevice(d.device_id)}
                          className="accent-emerald-500"
                        />
                        <span className="text-zinc-300 truncate">
                          {d.model || d.device_id}
                        </span>
                        <span className="text-[10px] text-zinc-600 mono ml-auto">
                          {d.device_id}
                        </span>
                      </label>
                    ))
                  )}
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setEditDialog(null)}
                className="px-4 py-1.5 text-xs rounded border border-main text-zinc-400 hover:text-strong transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!formName || saving}
                className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2"
              >
                {saving && <Loader className="w-3 h-3 animate-spin" />}
                {editDialog.mode === 'create' ? 'Create' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk action dialog */}
      {bulkDialog && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-card border border-main rounded-lg w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-sm font-bold">
                Bulk Action — {bulkDialog.name}
              </h3>
              <button
                onClick={() => setBulkDialog(null)}
                className="text-zinc-500 hover:text-strong transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-zinc-400 mb-4">
              {(bulkDialog.device_ids || []).length} device(s) in this group
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
                  Action
                </label>
                <select
                  value={bulkAction}
                  onChange={(e) => setBulkAction(e.target.value)}
                  className="w-full bg-body border border-main px-3 py-2 text-xs rounded focus:outline-none"
                >
                  <option value="command">Run Command</option>
                  <option value="install">Install Agent</option>
                  <option value="reboot">Reboot All</option>
                </select>
              </div>

              {bulkAction === 'command' && (
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
                    Shell Command
                  </label>
                  <input
                    value={bulkCommand}
                    onChange={(e) => setBulkCommand(e.target.value)}
                    className="w-full bg-body border border-main px-3 py-2 text-xs rounded focus:outline-none mono"
                    placeholder="getprop ro.product.model"
                  />
                </div>
              )}

              <button
                onClick={executeBulk}
                disabled={bulkRunning || (bulkAction === 'command' && !bulkCommand)}
                className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded transition-colors flex items-center justify-center gap-2"
              >
                {bulkRunning ? (
                  <><Loader className="w-3 h-3 animate-spin" /> Executing...</>
                ) : (
                  <><Play className="w-3 h-3" /> Execute</>
                )}
              </button>

              {/* Results table */}
              {bulkResults && (
                <div className="bg-body border border-main rounded overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-main text-[10px] text-zinc-500 uppercase">
                        <th className="text-left px-3 py-2 font-bold">Device</th>
                        <th className="text-left px-3 py-2 font-bold">Status</th>
                        <th className="text-left px-3 py-2 font-bold">Output</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bulkResults.map((r, i) => (
                        <tr key={i} className="border-b border-main">
                          <td className="px-3 py-2 mono text-zinc-400">{r.device_id}</td>
                          <td className="px-3 py-2">
                            {r.status === 'ok' ? (
                              <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                            ) : (
                              <XCircle className="w-3.5 h-3.5 text-red-500" />
                            )}
                          </td>
                          <td className="px-3 py-2 mono text-zinc-500 truncate max-w-[250px]">
                            {r.output || r.error || '--'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="flex justify-end mt-4">
              <button
                onClick={() => setBulkDialog(null)}
                className="px-4 py-1.5 text-xs rounded border border-main text-zinc-400 hover:text-strong transition-colors"
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
