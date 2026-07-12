// API Keys pane (plan 20): server-issued, scoped, revocable API keys. Admin-only.
//
// Lists keys (prefix + scopes + status + last-used), creates new keys from the scope
// catalog, rotates and revokes. Raw keys (dk_...) are returned by the backend exactly
// once — at create/rotate time — so they get a highlighted copy-me-now box.
import React, { useCallback, useEffect, useState } from 'react'
import { KeyRound, Plus, Trash2, RotateCw, Copy, Check, Loader2 } from 'lucide-react'
import { Pane, Field, TextInput } from './fields'
import { api } from '../../api'

const errMsg = (e) =>
  (e && e.body && (e.body.error || e.body.detail)) || (e && e.message) || 'Request failed'

const fmtWhen = (iso) => {
  if (!iso) return 'never'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function CopyButton({ text, title = 'Copy' }) {
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
      title={title}
      className="p-2 text-zinc-400 hover:text-strong border border-alt rounded-md"
    >
      {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
    </button>
  )
}

function StatusBadge({ status }) {
  const styles = {
    active: 'text-emerald-400 border-emerald-400/30',
    revoked: 'text-red-400 border-red-400/30',
    expired: 'text-zinc-500 border-alt',
  }
  return (
    <span
      className={`text-[10px] uppercase tracking-wide border rounded-full px-2 py-0.5 ${
        styles[status] || 'text-zinc-400 border-alt'
      }`}
    >
      {status}
    </span>
  )
}

// Shown once after create/rotate — the only time the raw key exists client-side.
function RawKeyBox({ action, rawKey, onDismiss }) {
  return (
    <div className="rounded-md border border-emerald-400/40 bg-card p-4 space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium text-emerald-400">
        <KeyRound className="w-4 h-4" />
        {action === 'rotated' ? 'Key rotated' : 'Key created'} — copy it now
      </div>
      <div className="flex items-center gap-2">
        <code className="flex-1 font-mono text-sm text-zinc-200 bg-body border border-alt rounded-md px-3 py-2 break-all">
          {rawKey}
        </code>
        <CopyButton text={rawKey} title="Copy key" />
      </div>
      <p className="text-xs text-zinc-500">
        This is the only time the full key is shown. Store it somewhere safe — you won't see it
        again.
      </p>
      <button type="button" onClick={onDismiss} className="text-xs text-zinc-400 hover:text-strong">
        Dismiss
      </button>
    </div>
  )
}

// Receives { settings, save } like every Settings pane; this pane manages its own data.
export default function ApiKeysPane({ register }) {
  const reg = register || (() => ({}))
  const [keys, setKeys] = useState([])
  const [scopeCatalog, setScopeCatalog] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [selectedScopes, setSelectedScopes] = useState([])
  const [expiresDays, setExpiresDays] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)

  const [newKey, setNewKey] = useState(null) // { action: 'created'|'rotated', key: 'dk_...' }
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(async () => {
    try {
      const [keysRes, scopesRes] = await Promise.all([api.getApiKeys(), api.getApiKeyScopes()])
      setKeys(keysRes.api_keys || [])
      setScopeCatalog(scopesRes.scopes || [])
      setError(null)
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const toggleScope = (scope) => {
    setSelectedScopes((cur) =>
      cur.includes(scope) ? cur.filter((s) => s !== scope) : [...cur, scope]
    )
  }

  const create = async (e) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || selectedScopes.length === 0) return
    setCreating(true)
    setCreateError(null)
    try {
      const payload = { name: trimmed, scopes: selectedScopes }
      const days = Number(expiresDays)
      if (expiresDays !== '' && Number.isFinite(days) && days > 0) {
        payload.expires_in_days = Math.floor(days)
      }
      const res = await api.createApiKey(payload)
      setNewKey({ action: 'created', key: res.api_key?.key })
      setName('')
      setSelectedScopes([])
      setExpiresDays('')
      setShowCreate(false)
      await load()
    } catch (err) {
      setCreateError(errMsg(err))
    } finally {
      setCreating(false)
    }
  }

  const rotate = async (k) => {
    if (!window.confirm(`Rotate "${k.name}"? The current key stops working immediately.`)) return
    setBusyId(k.id)
    try {
      const res = await api.rotateApiKey(k.id)
      setNewKey({ action: 'rotated', key: res.api_key?.key })
      setError(null)
      await load()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusyId(null)
    }
  }

  const revoke = async (k) => {
    if (!window.confirm(`Revoke "${k.name}"? Clients using it will lose access.`)) return
    setBusyId(k.id)
    try {
      await api.revokeApiKey(k.id)
      setError(null)
      await load()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusyId(null)
    }
  }

  if (loading) {
    return (
      <Pane title="API Keys" description="Scoped, revocable keys for programmatic access.">
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading keys…
        </div>
      </Pane>
    )
  }

  return (
    <Pane
      title="API Keys"
      description="Server-issued keys with per-scope permissions. Send them as X-API-Key; revoke or rotate at any time."
    >
      {error && <p className="text-sm text-red-400">{error}</p>}

      {newKey && newKey.key && (
        <RawKeyBox action={newKey.action} rawKey={newKey.key} onDismiss={() => setNewKey(null)} />
      )}

      {/* Key list */}
      <div className="space-y-3" {...reg('api-keys')}>
        {keys.length === 0 && (
          <p className="text-sm text-zinc-500">No API keys yet. Create one to get started.</p>
        )}
        {keys.map((k) => {
          const inactive = k.status !== 'active'
          return (
            <div
              key={k.id}
              className={`border border-main rounded-md bg-card p-4 ${
                inactive ? 'opacity-50' : ''
              }`}
            >
              <div className="flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-zinc-500" />
                <span className="text-sm font-medium text-zinc-200">{k.name}</span>
                <code className="font-mono text-xs text-zinc-500">{k.prefix}…</code>
                <StatusBadge status={k.status} />
                <div className="ml-auto flex items-center gap-1.5">
                  {k.status === 'active' && (
                    <>
                      <button
                        type="button"
                        onClick={() => rotate(k)}
                        disabled={busyId === k.id}
                        title="Rotate (issues a new key, revokes this one)"
                        className="border border-alt rounded-md px-3 py-1.5 text-sm text-zinc-400 hover:text-strong disabled:opacity-40 flex items-center gap-1.5"
                      >
                        {busyId === k.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <RotateCw className="w-4 h-4" />
                        )}
                        Rotate
                      </button>
                      <button
                        type="button"
                        onClick={() => revoke(k)}
                        disabled={busyId === k.id}
                        title="Revoke"
                        className="border border-alt rounded-md px-3 py-1.5 text-sm text-red-400 hover:text-red-300 disabled:opacity-40 flex items-center gap-1.5"
                      >
                        <Trash2 className="w-4 h-4" />
                        Revoke
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {(k.scopes || []).map((s) => (
                  <span
                    key={s}
                    className="font-mono text-[10px] bg-hover border border-main rounded px-1.5 py-0.5 text-zinc-400"
                  >
                    {s}
                  </span>
                ))}
              </div>
              <p className="mt-2 text-xs text-zinc-500">
                Created {fmtWhen(k.created_at)} · Last used {fmtWhen(k.last_used_at)}
                {k.last_used_ip ? ` from ${k.last_used_ip}` : ''}
              </p>
            </div>
          )
        })}
      </div>

      {/* Create key */}
      {!showCreate ? (
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="bg-white text-black text-sm font-semibold px-4 py-2 rounded-md hover:bg-zinc-200 transition-colors flex items-center gap-1.5"
        >
          <Plus className="w-4 h-4" /> Create key
        </button>
      ) : (
        <form
          onSubmit={create}
          className="border border-main rounded-md bg-card p-4 space-y-4"
        >
          <div className="text-sm font-medium text-zinc-200 flex items-center gap-1.5">
            <Plus className="w-4 h-4" /> Create key
          </div>

          <Field label="Name" help="A label so you can tell keys apart later." htmlFor="ak-name">
            <TextInput id="ak-name" value={name} onChange={setName} placeholder="e.g. CI deploys" />
          </Field>

          <div>
            <span className="text-sm font-medium text-zinc-200 block">Scopes</span>
            <p className="text-xs text-zinc-500 mt-0.5 mb-2">
              What this key may do. <span className="font-mono">*</span> grants full access.
            </p>
            <div className="grid grid-cols-2 gap-1.5 max-h-48 overflow-y-auto border border-main rounded-md bg-body p-3">
              {scopeCatalog.map((s) => (
                <label
                  key={s}
                  className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedScopes.includes(s)}
                    onChange={() => toggleScope(s)}
                    className="accent-white"
                  />
                  <span className="font-mono text-xs">{s}</span>
                  {s === '*' && <span className="text-[10px] text-zinc-500">(full access)</span>}
                </label>
              ))}
            </div>
          </div>

          <Field
            label="Expires in"
            help="Optional. Days until the key expires; leave blank for no expiry."
            htmlFor="ak-expiry"
          >
            <div className="flex items-center gap-2">
              <TextInput
                id="ak-expiry"
                type="number"
                value={expiresDays}
                onChange={setExpiresDays}
                placeholder="days"
                className="w-24"
              />
              <span className="text-xs text-zinc-500">days</span>
            </div>
          </Field>

          {createError && <p className="text-sm text-red-400">{createError}</p>}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={creating || !name.trim() || selectedScopes.length === 0}
              className="bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors flex items-center gap-1.5"
            >
              {creating && <Loader2 className="w-4 h-4 animate-spin" />}
              {creating ? 'Creating…' : 'Create key'}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowCreate(false)
                setCreateError(null)
              }}
              className="text-sm text-zinc-400 hover:text-strong px-2 py-2"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </Pane>
  )
}
