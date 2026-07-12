// Users & Invitations pane (plan 20 identity/RBAC). Admin-only: manages local user
// accounts (role, active state, password resets, per-user permission overrides) and
// invitation links. Fetches its own data — the shared settings/save props are unused.
import React, { useCallback, useEffect, useState } from 'react'
import {
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  KeyRound,
  Loader2,
  Mail,
  Shield,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users as UsersIcon,
} from 'lucide-react'
import { Pane, Field, TextInput, Select, Toggle } from './fields'
import { api } from '../../api'

const FALLBACK_FEATURES = [
  'devices',
  'automations',
  'extensions',
  'commands',
  'metrics',
  'notifications',
  'settings',
  'agents',
]
const FALLBACK_ROLES = ['admin', 'operator', 'viewer']

const ROLE_BADGE = {
  admin: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  operator: 'bg-zinc-800 text-zinc-300 border-alt',
  viewer: 'bg-zinc-900 text-zinc-500 border-alt',
}

const INVITE_STATUS = {
  pending: 'text-zinc-300',
  accepted: 'text-emerald-400',
  revoked: 'text-red-400',
  expired: 'text-zinc-500',
}

const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '')

const fmtDate = (s) => {
  if (!s) return null
  const d = new Date(s)
  if (isNaN(d.getTime())) return null
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function RoleBadge({ role }) {
  return (
    <span
      className={`text-[10px] uppercase tracking-wide border rounded px-1.5 py-0.5 ${
        ROLE_BADGE[role] || ROLE_BADGE.viewer
      }`}
    >
      {role}
    </span>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      title="Copy"
      className="p-2 text-zinc-400 hover:text-white border border-alt rounded-md shrink-0"
    >
      {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
    </button>
  )
}

// Compact read/write checkbox matrix over the permission features. Enforces
// write ⇒ read: checking write auto-checks read, unchecking read clears write.
function PermMatrix({ features, initial, busy, onSave }) {
  const build = useCallback(() => {
    const m = {}
    for (const f of features) {
      m[f] = { read: !!(initial && initial[f] && initial[f].read), write: !!(initial && initial[f] && initial[f].write) }
    }
    return m
  }, [features, initial])

  const [matrix, setMatrix] = useState(build)
  const dirty = JSON.stringify(matrix) !== JSON.stringify(build())

  const setPerm = (feature, kind, val) =>
    setMatrix((m) => {
      const next = { ...m[feature], [kind]: val }
      if (kind === 'write' && val) next.read = true
      if (kind === 'read' && !val) next.write = false
      return { ...m, [feature]: next }
    })

  return (
    <div className="border border-main rounded-md bg-black p-3">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-zinc-500">
            <th className="text-left font-medium pb-2">Feature</th>
            <th className="text-center font-medium pb-2 w-16">Read</th>
            <th className="text-center font-medium pb-2 w-16">Write</th>
          </tr>
        </thead>
        <tbody>
          {features.map((f) => (
            <tr key={f} className="border-t border-main">
              <td className="py-1.5 text-zinc-300 capitalize">{f}</td>
              <td className="py-1.5 text-center">
                <input
                  type="checkbox"
                  className="accent-emerald-500"
                  checked={matrix[f]?.read || false}
                  onChange={(e) => setPerm(f, 'read', e.target.checked)}
                />
              </td>
              <td className="py-1.5 text-center">
                <input
                  type="checkbox"
                  className="accent-emerald-500"
                  checked={matrix[f]?.write || false}
                  onChange={(e) => setPerm(f, 'write', e.target.checked)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center gap-2 pt-2 mt-1 border-t border-main">
        <button
          type="button"
          disabled={!dirty || busy}
          onClick={() => onSave(matrix)}
          className="bg-white text-black text-xs font-semibold px-3 py-1.5 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors"
        >
          Save permissions
        </button>
        {dirty && (
          <button
            type="button"
            onClick={() => setMatrix(build())}
            className="text-xs text-zinc-400 hover:text-white px-2 py-1.5"
          >
            Discard
          </button>
        )}
      </div>
    </div>
  )
}

function UserRow({ user, roleOptions, features, onChanged, onError }) {
  const [open, setOpen] = useState(false)
  const [showPerms, setShowPerms] = useState(false)
  const [busy, setBusy] = useState(false)

  const run = async (fn) => {
    setBusy(true)
    onError(null)
    try {
      await fn()
      await onChanged()
    } catch (e) {
      onError(e.message || 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  const resetPassword = () => {
    const pw = window.prompt(`New password for "${user.username}":`)
    if (!pw) return
    run(() => api.updateUser(user.id, { password: pw }))
  }

  const remove = () => {
    if (!window.confirm(`Delete user "${user.username}"? This cannot be undone.`)) return
    run(() => api.deleteUser(user.id))
  }

  return (
    <div className="px-3 py-2.5">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          title={open ? 'Collapse' : 'Edit user'}
          className="text-zinc-500 hover:text-white shrink-0"
        >
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zinc-200 truncate">{user.username}</span>
            <RoleBadge role={user.role} />
            {!user.is_active && (
              <span className="text-[10px] uppercase tracking-wide text-red-400 border border-red-500/20 bg-red-500/10 rounded px-1.5 py-0.5">
                Inactive
              </span>
            )}
          </div>
          <div className="text-xs text-zinc-500 mt-0.5 truncate">
            {user.email ? `${user.email} · ` : ''}
            Last login: {fmtDate(user.last_login_at) || 'never'}
          </div>
        </div>
        <span title={user.totp_enabled ? '2FA enabled' : '2FA off'} className="shrink-0">
          {user.totp_enabled ? (
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          ) : (
            <Shield className="w-4 h-4 text-zinc-600" />
          )}
        </span>
        {busy && <Loader2 className="w-4 h-4 animate-spin text-zinc-500 shrink-0" />}
      </div>

      {open && (
        <div className="mt-3 ml-7 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className="w-36">
              <Select
                id={`role-${user.id}`}
                value={user.role}
                onChange={(r) => {
                  if (r !== user.role) run(() => api.updateUser(user.id, { role: r }))
                }}
                options={roleOptions}
              />
            </div>
            <label className="flex items-center gap-2 text-xs text-zinc-400">
              <Toggle
                id={`active-${user.id}`}
                checked={!!user.is_active}
                onChange={(v) => run(() => api.updateUser(user.id, { is_active: v }))}
              />
              Active
            </label>
            <button
              type="button"
              onClick={resetPassword}
              disabled={busy}
              className="border border-alt rounded-md px-3 py-1.5 text-sm text-zinc-300 hover:text-white flex items-center gap-1.5 disabled:opacity-40"
            >
              <KeyRound className="w-4 h-4" /> Reset password
            </button>
            <button
              type="button"
              onClick={remove}
              disabled={busy}
              className="border border-alt rounded-md px-3 py-1.5 text-sm text-red-400 hover:border-red-500/40 flex items-center gap-1.5 disabled:opacity-40"
            >
              <Trash2 className="w-4 h-4" /> Delete
            </button>
          </div>

          {user.role !== 'admin' && (
            <div>
              <button
                type="button"
                onClick={() => setShowPerms((s) => !s)}
                className="text-xs text-zinc-400 hover:text-white flex items-center gap-1 mb-2"
              >
                {showPerms ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                Permission overrides
              </button>
              {showPerms && (
                <PermMatrix
                  features={features}
                  initial={user.effective_permissions}
                  busy={busy}
                  onSave={(perms) => run(() => api.updateUser(user.id, { permissions: perms }))}
                />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function InviteRow({ invite, onChanged, onError }) {
  const [busy, setBusy] = useState(false)

  const revoke = async () => {
    if (!window.confirm('Revoke this invitation? The link will stop working.')) return
    setBusy(true)
    onError(null)
    try {
      await api.revokeInvitation(invite.id)
      await onChanged()
    } catch (e) {
      onError(e.message || 'Failed to revoke invitation')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="px-3 py-2.5 flex items-center gap-3">
      <Mail className="w-4 h-4 text-zinc-600 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-zinc-200 truncate">
            {invite.email || 'Anyone with the link'}
          </span>
          <RoleBadge role={invite.role} />
        </div>
        <div className="text-xs text-zinc-500 mt-0.5">
          <span className={INVITE_STATUS[invite.status] || 'text-zinc-400'}>{cap(invite.status)}</span>
          {invite.expires_at ? ` · expires ${fmtDate(invite.expires_at)}` : ''}
        </div>
      </div>
      {invite.status === 'pending' && (
        <button
          type="button"
          onClick={revoke}
          disabled={busy}
          className="border border-alt rounded-md px-3 py-1.5 text-sm text-red-400 hover:border-red-500/40 flex items-center gap-1.5 disabled:opacity-40 shrink-0"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
          Revoke
        </button>
      )}
    </div>
  )
}

export default function Users({ settings, save, register }) {
  const reg = register || (() => ({}))
  const [users, setUsers] = useState([])
  const [invites, setInvites] = useState([])
  const [schema, setSchema] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [userErr, setUserErr] = useState(null)
  const [inviteErr, setInviteErr] = useState(null)

  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ username: '', password: '', role: 'viewer', email: '' })
  const [creating, setCreating] = useState(false)

  const [showInviteForm, setShowInviteForm] = useState(false)
  const [inviteForm, setInviteForm] = useState({ role: 'viewer', email: '', days: '7' })
  const [inviting, setInviting] = useState(false)
  const [inviteLink, setInviteLink] = useState(null)

  const refreshUsers = useCallback(async () => {
    const d = await api.getUsers()
    setUsers(d.users || [])
  }, [])

  const refreshInvites = useCallback(async () => {
    const d = await api.getInvitations()
    setInvites(d.invitations || [])
  }, [])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [u, i, s] = await Promise.all([
          api.getUsers(),
          api.getInvitations(),
          api.getPermissionSchema().catch(() => null),
        ])
        if (!alive) return
        setUsers(u.users || [])
        setInvites(i.invitations || [])
        setSchema(s)
      } catch (e) {
        if (!alive) return
        setError(
          e.status === 403
            ? 'Admin access is required to manage users.'
            : e.message || 'Failed to load users'
        )
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  const roles = schema?.roles?.length ? schema.roles : FALLBACK_ROLES
  const features = schema?.features?.length ? schema.features : FALLBACK_FEATURES
  const roleOptions = roles.map((r) => ({ value: r, label: cap(r) }))

  const addUser = async () => {
    setCreating(true)
    setUserErr(null)
    try {
      const payload = { username: form.username.trim(), password: form.password, role: form.role }
      if (form.email.trim()) payload.email = form.email.trim()
      await api.createUser(payload)
      setForm({ username: '', password: '', role: 'viewer', email: '' })
      setShowAdd(false)
      await refreshUsers()
    } catch (e) {
      setUserErr(e.message || 'Failed to create user')
    } finally {
      setCreating(false)
    }
  }

  const createInvite = async () => {
    setInviting(true)
    setInviteErr(null)
    setInviteLink(null)
    try {
      const payload = { role: inviteForm.role, expires_in_days: Number(inviteForm.days) || 7 }
      if (inviteForm.email.trim()) payload.email = inviteForm.email.trim()
      const d = await api.createInvitation(payload)
      const token = d?.invitation?.token
      if (token) setInviteLink(`${window.location.origin}/?invite=${token}`)
      setInviteForm({ role: 'viewer', email: '', days: '7' })
      setShowInviteForm(false)
      await refreshInvites()
    } catch (e) {
      setInviteErr(e.message || 'Failed to create invitation')
    } finally {
      setInviting(false)
    }
  }

  if (loading) {
    return (
      <Pane title="Users" description="Manage accounts, roles, permissions, and invitation links.">
        <div className="flex items-center justify-center gap-2 text-sm text-zinc-500 py-10">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading users…
        </div>
      </Pane>
    )
  }

  if (error) {
    return (
      <Pane title="Users" description="Manage accounts, roles, permissions, and invitation links.">
        <div className="rounded-md border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-400">
          {error}
        </div>
      </Pane>
    )
  }

  return (
    <Pane
      title="Users"
      description="Manage accounts, roles, per-user permissions, and invitation links. Admin only."
    >
      {/* ------------------------------ Accounts ------------------------------ */}
      <section {...reg('users-accounts')}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
            <UsersIcon className="w-4 h-4 text-zinc-500" /> Accounts
            <span className="text-xs font-normal text-zinc-500">({users.length})</span>
          </h3>
          <button
            type="button"
            onClick={() => {
              setShowAdd((s) => !s)
              setUserErr(null)
            }}
            className="border border-alt rounded-md px-3 py-1.5 text-sm text-zinc-300 hover:text-white flex items-center gap-1.5"
          >
            <UserPlus className="w-4 h-4" /> Add user
          </button>
        </div>

        {userErr && <div className="text-xs text-red-400 mb-2">{userErr}</div>}

        {showAdd && (
          <div className="border border-main rounded-md bg-zinc-950 p-4 mb-3 space-y-4">
            <Field label="Username" htmlFor="nu-username">
              <TextInput
                id="nu-username"
                value={form.username}
                onChange={(v) => setForm((f) => ({ ...f, username: v }))}
                placeholder="jane"
              />
            </Field>
            <Field label="Password" htmlFor="nu-password">
              <TextInput
                id="nu-password"
                type="password"
                value={form.password}
                onChange={(v) => setForm((f) => ({ ...f, password: v }))}
                placeholder="••••••••"
              />
            </Field>
            <Field label="Role" htmlFor="nu-role">
              <div className="w-full">
                <Select
                  id="nu-role"
                  value={form.role}
                  onChange={(v) => setForm((f) => ({ ...f, role: v }))}
                  options={roleOptions}
                />
              </div>
            </Field>
            <Field label="Email" help="Optional" htmlFor="nu-email">
              <TextInput
                id="nu-email"
                value={form.email}
                onChange={(v) => setForm((f) => ({ ...f, email: v }))}
                placeholder="jane@example.com"
              />
            </Field>
            <div className="flex items-center gap-2 pt-1">
              <button
                type="button"
                onClick={addUser}
                disabled={creating || !form.username.trim() || !form.password}
                className="bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors flex items-center gap-2"
              >
                {creating && <Loader2 className="w-4 h-4 animate-spin" />} Create user
              </button>
              <button
                type="button"
                onClick={() => setShowAdd(false)}
                className="text-sm text-zinc-400 hover:text-white px-2 py-2"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="border border-main rounded-md bg-zinc-950 divide-y divide-zinc-800">
          {users.map((u) => (
            <UserRow
              key={u.id}
              user={u}
              roleOptions={roleOptions}
              features={features}
              onChanged={refreshUsers}
              onError={setUserErr}
            />
          ))}
          {users.length === 0 && (
            <div className="px-3 py-6 text-center text-xs text-zinc-500">No users yet.</div>
          )}
        </div>
      </section>

      {/* ---------------------------- Invitations ----------------------------- */}
      <section {...reg('user-invitations')}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
            <Mail className="w-4 h-4 text-zinc-500" /> Invitations
            <span className="text-xs font-normal text-zinc-500">({invites.length})</span>
          </h3>
          <button
            type="button"
            onClick={() => {
              setShowInviteForm((s) => !s)
              setInviteErr(null)
            }}
            className="border border-alt rounded-md px-3 py-1.5 text-sm text-zinc-300 hover:text-white flex items-center gap-1.5"
          >
            <UserPlus className="w-4 h-4" /> Create invite
          </button>
        </div>

        {inviteErr && <div className="text-xs text-red-400 mb-2">{inviteErr}</div>}

        {inviteLink && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 mb-3">
            <p className="text-xs text-emerald-400 mb-2">
              Invite created — copy this link now, it will not be shown again.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 truncate font-mono text-xs text-zinc-200 bg-black border border-alt rounded-md px-2 py-2">
                {inviteLink}
              </code>
              <CopyButton text={inviteLink} />
            </div>
          </div>
        )}

        {showInviteForm && (
          <div className="border border-main rounded-md bg-zinc-950 p-4 mb-3 space-y-4">
            <Field label="Role" help="Granted to whoever accepts the invite." htmlFor="inv-role">
              <div className="w-full">
                <Select
                  id="inv-role"
                  value={inviteForm.role}
                  onChange={(v) => setInviteForm((f) => ({ ...f, role: v }))}
                  options={roleOptions}
                />
              </div>
            </Field>
            <Field label="Email" help="Optional — locks the invite to this address." htmlFor="inv-email">
              <TextInput
                id="inv-email"
                value={inviteForm.email}
                onChange={(v) => setInviteForm((f) => ({ ...f, email: v }))}
                placeholder="jane@example.com"
              />
            </Field>
            <Field label="Expires in" help="Days until the link stops working." htmlFor="inv-days">
              <TextInput
                id="inv-days"
                type="number"
                value={inviteForm.days}
                onChange={(v) => setInviteForm((f) => ({ ...f, days: v }))}
                placeholder="7"
              />
            </Field>
            <div className="flex items-center gap-2 pt-1">
              <button
                type="button"
                onClick={createInvite}
                disabled={inviting}
                className="bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors flex items-center gap-2"
              >
                {inviting && <Loader2 className="w-4 h-4 animate-spin" />} Create invite
              </button>
              <button
                type="button"
                onClick={() => setShowInviteForm(false)}
                className="text-sm text-zinc-400 hover:text-white px-2 py-2"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="border border-main rounded-md bg-zinc-950 divide-y divide-zinc-800">
          {invites.map((inv) => (
            <InviteRow key={inv.id} invite={inv} onChanged={refreshInvites} onError={setInviteErr} />
          ))}
          {invites.length === 0 && (
            <div className="px-3 py-6 text-center text-xs text-zinc-500">No invitations yet.</div>
          )}
        </div>
      </section>
    </Pane>
  )
}
