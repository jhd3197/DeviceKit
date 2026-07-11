// Workspaces pane (plan 20): create/delete workspaces, manage members and their roles,
// and pick the browser's *active* workspace. The active workspace is persisted to
// localStorage via setActiveWorkspace() and drives the X-Workspace-Id header that scopes
// every API request. Workspace roles only narrow permissions — they never elevate a
// user's global role.
import React, { useEffect, useMemo, useState, useCallback } from 'react'
import { Building2, Users, Plus, Trash2, Loader2, Check } from 'lucide-react'
import { Pane, Select } from './fields'
import { api, getActiveWorkspace, setActiveWorkspace } from '../../api'

const ROLE_OPTIONS = [
  { value: 'owner', label: 'Owner' },
  { value: 'admin', label: 'Admin' },
  { value: 'member', label: 'Member' },
  { value: 'viewer', label: 'Viewer' },
]

function fmtTime(ts) {
  if (!ts) return ''
  const n = Number(ts)
  if (!Number.isFinite(n)) return String(ts)
  return new Date(n * 1000).toLocaleString()
}

export default function Workspaces({ settings, save }) {
  const [workspaces, setWorkspaces] = useState([])
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [activeId, setActiveId] = useState(() => getActiveWorkspace() || '')
  const [selectedId, setSelectedId] = useState(null)

  const [members, setMembers] = useState([])
  const [membersLoading, setMembersLoading] = useState(false)
  const [membersError, setMembersError] = useState(null)

  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)

  const [addUserId, setAddUserId] = useState('')
  const [addRole, setAddRole] = useState('member')
  const [adding, setAdding] = useState(false)
  const [busyMember, setBusyMember] = useState(null)

  const userById = useMemo(() => {
    const m = {}
    for (const u of users) m[u.id] = u
    return m
  }, [users])

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [ws, us] = await Promise.all([api.getWorkspaces(), api.getUsers()])
      setWorkspaces(ws.workspaces || [])
      setUsers(us.users || [])
    } catch (e) {
      setError(e.message || 'Failed to load workspaces')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  const loadMembers = useCallback(async (id) => {
    setMembersLoading(true)
    setMembersError(null)
    try {
      const res = await api.getWorkspaceMembers(id)
      setMembers(res.members || [])
    } catch (e) {
      setMembersError(e.message || 'Failed to load members')
    } finally {
      setMembersLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectedId) loadMembers(selectedId)
    else {
      setMembers([])
      setMembersError(null)
    }
  }, [selectedId, loadMembers])

  const makeActive = (id) => {
    setActiveWorkspace(id)
    setActiveId(id)
  }

  const clearActive = () => {
    setActiveWorkspace('')
    setActiveId('')
  }

  const create = async () => {
    const name = newName.trim()
    if (!name || creating) return
    setCreating(true)
    setError(null)
    try {
      const res = await api.createWorkspace({ name })
      if (res.workspace) setWorkspaces((ws) => [...ws, res.workspace])
      setNewName('')
    } catch (e) {
      setError(e.message || 'Failed to create workspace')
    } finally {
      setCreating(false)
    }
  }

  const remove = async (w) => {
    if (!window.confirm(`Delete workspace "${w.name}"? This cannot be undone.`)) return
    setError(null)
    try {
      await api.deleteWorkspace(w.id)
      setWorkspaces((ws) => ws.filter((x) => x.id !== w.id))
      if (selectedId === w.id) setSelectedId(null)
      if (activeId === w.id) clearActive()
    } catch (e) {
      setError(e.message || 'Failed to delete workspace')
    }
  }

  const addMember = async () => {
    if (!addUserId || !selectedId || adding) return
    setAdding(true)
    setMembersError(null)
    try {
      const res = await api.addWorkspaceMember(selectedId, { user_id: addUserId, role: addRole })
      if (res.member) setMembers((ms) => [...ms, res.member])
      setAddUserId('')
      setAddRole('member')
    } catch (e) {
      setMembersError(e.message || 'Failed to add member')
    } finally {
      setAdding(false)
    }
  }

  const changeRole = async (member, role) => {
    setBusyMember(member.id)
    setMembersError(null)
    try {
      const res = await api.updateWorkspaceMember(selectedId, member.user_id, role)
      setMembers((ms) => ms.map((m) => (m.id === member.id ? { ...m, ...(res.member || { role }) } : m)))
    } catch (e) {
      setMembersError(e.message || 'Failed to update role')
    } finally {
      setBusyMember(null)
    }
  }

  const removeMember = async (member) => {
    const name = userById[member.user_id]?.username || member.user_id
    if (!window.confirm(`Remove ${name} from this workspace?`)) return
    setBusyMember(member.id)
    setMembersError(null)
    try {
      await api.removeWorkspaceMember(selectedId, member.user_id)
      setMembers((ms) => ms.filter((m) => m.id !== member.id))
    } catch (e) {
      setMembersError(e.message || 'Failed to remove member')
    } finally {
      setBusyMember(null)
    }
  }

  const selected = workspaces.find((w) => w.id === selectedId) || null
  const active = workspaces.find((w) => w.id === activeId) || null
  const candidates = users.filter((u) => !members.some((m) => m.user_id === u.id))

  return (
    <Pane
      title="Workspaces"
      description="Group devices and members into scoped workspaces. The active workspace is stored in this browser and sent as X-Workspace-Id with every request."
    >
      {error && <div className="text-sm text-red-400">{error}</div>}

      {/* Active workspace banner */}
      <div className="flex items-center justify-between rounded-md border border-main bg-zinc-950 px-4 py-3">
        <div className="flex items-center gap-2 text-sm">
          <Building2 className="w-4 h-4 text-zinc-500" />
          {activeId ? (
            <span className="text-zinc-200">
              Active workspace:{' '}
              <span className="font-medium text-emerald-400">{active ? active.name : activeId}</span>
            </span>
          ) : (
            <span className="text-zinc-500">No active workspace — requests are unscoped.</span>
          )}
        </div>
        {activeId && (
          <button
            type="button"
            onClick={clearActive}
            className="border border-alt rounded-md px-3 py-1.5 text-sm text-zinc-400 hover:text-white"
          >
            Clear
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-500 py-6">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading workspaces…
        </div>
      ) : (
        <div className="rounded-md border border-main divide-y divide-zinc-800/60 overflow-hidden">
          {workspaces.length === 0 && (
            <div className="px-4 py-6 text-sm text-zinc-500">No workspaces yet. Create one below.</div>
          )}
          {workspaces.map((w) => (
            <div key={w.id} className={w.id === selectedId ? 'bg-zinc-900/60' : 'bg-zinc-950'}>
              <div
                role="button"
                tabIndex={0}
                onClick={() => setSelectedId((id) => (id === w.id ? null : w.id))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') setSelectedId((id) => (id === w.id ? null : w.id))
                }}
                className="w-full flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-zinc-900/40"
              >
                <Building2 className="w-4 h-4 text-zinc-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-zinc-200 truncate">{w.name}</div>
                  <div className="text-xs text-zinc-500 truncate">
                    {w.slug}
                    {w.status && w.status !== 'active' && (
                      <span className="text-amber-400 ml-2">{w.status}</span>
                    )}
                  </div>
                </div>
                {w.id === activeId ? (
                  <span className="flex items-center gap-1 text-xs text-emerald-400 shrink-0">
                    <Check className="w-4 h-4" /> Active
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      makeActive(w.id)
                    }}
                    className="border border-alt rounded-md px-3 py-1.5 text-sm text-zinc-400 hover:text-white shrink-0"
                  >
                    Set active
                  </button>
                )}
                <button
                  type="button"
                  title="Delete workspace"
                  onClick={(e) => {
                    e.stopPropagation()
                    remove(w)
                  }}
                  className="p-2 text-zinc-500 hover:text-red-400 border border-alt rounded-md shrink-0"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              {/* Members panel for the selected workspace */}
              {w.id === selectedId && (
                <div className="border-t border-main px-4 py-4 space-y-4">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    <Users className="w-4 h-4" /> Members{selected ? ` — ${selected.name}` : ''}
                  </div>

                  {membersError && <div className="text-sm text-red-400">{membersError}</div>}

                  {membersLoading ? (
                    <div className="flex items-center gap-2 text-sm text-zinc-500">
                      <Loader2 className="w-4 h-4 animate-spin" /> Loading members…
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {members.length === 0 && (
                        <div className="text-sm text-zinc-500">No members yet.</div>
                      )}
                      {members.map((m) => (
                        <div
                          key={m.id}
                          className="flex items-center gap-3 rounded-md border border-alt bg-black px-3 py-2"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="text-sm text-zinc-200 truncate">
                              {userById[m.user_id]?.username || m.user_id}
                            </div>
                            <div className="text-xs text-zinc-500">Added {fmtTime(m.created_at)}</div>
                          </div>
                          <div className="w-28 shrink-0">
                            <Select
                              value={m.role}
                              onChange={(role) => changeRole(m, role)}
                              options={ROLE_OPTIONS}
                            />
                          </div>
                          <button
                            type="button"
                            title="Remove member"
                            disabled={busyMember === m.id}
                            onClick={() => removeMember(m)}
                            className="p-2 text-zinc-500 hover:text-red-400 border border-alt rounded-md disabled:opacity-40"
                          >
                            {busyMember === m.id ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                        </div>
                      ))}

                      {/* Add member */}
                      <div className="flex items-center gap-2 pt-1">
                        <div className="flex-1">
                          <Select
                            value={addUserId}
                            onChange={setAddUserId}
                            options={[
                              { value: '', label: candidates.length ? 'Select user…' : 'No users available' },
                              ...candidates.map((u) => ({ value: u.id, label: u.username })),
                            ]}
                          />
                        </div>
                        <div className="w-28">
                          <Select value={addRole} onChange={setAddRole} options={ROLE_OPTIONS} />
                        </div>
                        <button
                          type="button"
                          disabled={!addUserId || adding}
                          onClick={addMember}
                          className="flex items-center gap-1.5 border border-alt rounded-md px-3 py-1.5 text-sm text-zinc-200 hover:text-white disabled:opacity-40"
                        >
                          {adding ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Plus className="w-4 h-4" />
                          )}
                          Add
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create workspace */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') create()
          }}
          placeholder="New workspace name"
          className="flex-1 bg-black border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-accent"
        />
        <button
          type="button"
          disabled={!newName.trim() || creating}
          onClick={create}
          className="flex items-center gap-1.5 bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors"
        >
          {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          Create workspace
        </button>
      </div>

      <div className="rounded-md border border-main bg-card p-4 text-xs text-zinc-500 leading-relaxed">
        Workspace roles (owner, admin, member, viewer) only <span className="text-zinc-400">narrow</span>{' '}
        what a user can do inside that workspace — they never elevate a user beyond their global
        account permissions.
      </div>
    </Pane>
  )
}
