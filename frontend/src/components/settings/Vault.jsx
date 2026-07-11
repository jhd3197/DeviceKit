// Vault pane (plan 20): encrypted secrets vault. Admin-only.
//
// Left column lists vaults (create/delete); right column shows the selected vault's
// secrets. Values arrive masked (••••••••) — plaintext only comes back through the
// separate reveal endpoint, and is held in component state until toggled away.
// Values are Fernet-encrypted at rest on the server.
import React, { useCallback, useEffect, useState } from 'react'
import { Lock, Plus, Trash2, Copy, Check, Eye, EyeOff, Loader2 } from 'lucide-react'
import { Pane, TextInput } from './fields'
import { api } from '../../api'

const MASK = '••••••••'

const errMsg = (e) =>
  (e && e.body && (e.body.error || e.body.detail)) || (e && e.message) || 'Request failed'

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
      className="p-2 text-zinc-400 hover:text-white border border-alt rounded-md"
    >
      {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
    </button>
  )
}

// Receives { settings, save } like every Settings pane; this pane manages its own data.
export default function Vault() {
  const [vaults, setVaults] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [selectedId, setSelectedId] = useState(null)
  const [secrets, setSecrets] = useState([])
  const [secretsLoading, setSecretsLoading] = useState(false)
  const [secretsError, setSecretsError] = useState(null)

  // Create-vault form
  const [vaultName, setVaultName] = useState('')
  const [vaultDesc, setVaultDesc] = useState('')
  const [creatingVault, setCreatingVault] = useState(false)
  const [vaultBusy, setVaultBusy] = useState(null)

  // Add-secret form
  const [secretKey, setSecretKey] = useState('')
  const [secretValue, setSecretValue] = useState('')
  const [secretDesc, setSecretDesc] = useState('')
  const [savingSecret, setSavingSecret] = useState(false)

  // key -> { value: plaintext, shown: bool }; only populated after a reveal call.
  const [revealed, setRevealed] = useState({})
  const [revealBusy, setRevealBusy] = useState(null)
  const [secretBusy, setSecretBusy] = useState(null)

  const reloadVaults = useCallback(async () => {
    const res = await api.getVaults()
    setVaults(res.vaults || [])
    return res.vaults || []
  }, [])

  useEffect(() => {
    reloadVaults()
      .then(() => setError(null))
      .catch((e) => setError(errMsg(e)))
      .finally(() => setLoading(false))
  }, [reloadVaults])

  // Load secrets whenever the selection changes; drop any revealed plaintext.
  useEffect(() => {
    if (selectedId == null) {
      setSecrets([])
      setSecretsError(null)
      return undefined
    }
    let cancelled = false
    setSecretsLoading(true)
    setSecretsError(null)
    setRevealed({})
    api
      .getVaultSecrets(selectedId)
      .then((res) => {
        if (!cancelled) setSecrets(res.secrets || [])
      })
      .catch((e) => {
        if (!cancelled) setSecretsError(errMsg(e))
      })
      .finally(() => {
        if (!cancelled) setSecretsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedId])

  const reloadSecrets = async (vaultId) => {
    const res = await api.getVaultSecrets(vaultId)
    setSecrets(res.secrets || [])
  }

  const createVaultSubmit = async (e) => {
    e.preventDefault()
    const trimmed = vaultName.trim()
    if (!trimmed) return
    setCreatingVault(true)
    try {
      const payload = { name: trimmed }
      if (vaultDesc.trim()) payload.description = vaultDesc.trim()
      const res = await api.createVault(payload)
      setVaultName('')
      setVaultDesc('')
      setError(null)
      await reloadVaults()
      if (res.vault?.id != null) setSelectedId(res.vault.id)
    } catch (err) {
      setError(errMsg(err))
    } finally {
      setCreatingVault(false)
    }
  }

  const removeVault = async (v) => {
    if (!window.confirm(`Delete vault "${v.name}" and all its secrets? This cannot be undone.`)) {
      return
    }
    setVaultBusy(v.id)
    try {
      await api.deleteVault(v.id)
      if (selectedId === v.id) setSelectedId(null)
      setError(null)
      await reloadVaults()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setVaultBusy(null)
    }
  }

  const addSecret = async (e) => {
    e.preventDefault()
    const k = secretKey.trim()
    if (!k || !secretValue || selectedId == null) return
    setSavingSecret(true)
    setSecretsError(null)
    try {
      const payload = { key: k, value: secretValue }
      if (secretDesc.trim()) payload.description = secretDesc.trim()
      await api.setVaultSecret(selectedId, payload)
      setSecretKey('')
      setSecretValue('')
      setSecretDesc('')
      // A rotated value invalidates any previously revealed plaintext for this key.
      setRevealed((m) => {
        const next = { ...m }
        delete next[k]
        return next
      })
      await Promise.all([reloadSecrets(selectedId), reloadVaults()])
    } catch (err) {
      setSecretsError(errMsg(err))
    } finally {
      setSavingSecret(false)
    }
  }

  const toggleReveal = async (key) => {
    const existing = revealed[key]
    if (existing) {
      setRevealed((m) => ({ ...m, [key]: { ...existing, shown: !existing.shown } }))
      return
    }
    setRevealBusy(key)
    try {
      const res = await api.revealVaultSecret(selectedId, key)
      setRevealed((m) => ({ ...m, [key]: { value: res.secret?.value ?? '', shown: true } }))
      setSecretsError(null)
    } catch (e) {
      setSecretsError(errMsg(e))
    } finally {
      setRevealBusy(null)
    }
  }

  const removeSecret = async (key) => {
    if (!window.confirm(`Delete secret "${key}"? This cannot be undone.`)) return
    setSecretBusy(key)
    try {
      await api.deleteVaultSecret(selectedId, key)
      setRevealed((m) => {
        const next = { ...m }
        delete next[key]
        return next
      })
      setSecretsError(null)
      await Promise.all([reloadSecrets(selectedId), reloadVaults()])
    } catch (e) {
      setSecretsError(errMsg(e))
    } finally {
      setSecretBusy(null)
    }
  }

  if (loading) {
    return (
      <Pane title="Vault" description="Encrypted secrets storage for automations and agents.">
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading vaults…
        </div>
      </Pane>
    )
  }

  const selectedVault = vaults.find((v) => v.id === selectedId) || null

  return (
    <Pane
      title="Vault"
      description="Encrypted secrets storage. Group secrets into vaults; values are only decrypted on explicit reveal."
    >
      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="grid grid-cols-[14rem_1fr] gap-6 items-start">
        {/* Left: vault list + create */}
        <div className="space-y-3">
          {vaults.length === 0 && (
            <p className="text-xs text-zinc-500">No vaults yet. Create one below.</p>
          )}
          {vaults.map((v) => (
            <div key={v.id} className="relative group">
              <button
                type="button"
                onClick={() => setSelectedId(v.id)}
                className={`w-full text-left px-3 py-2 rounded-md border transition-colors ${
                  selectedId === v.id
                    ? 'border-zinc-500 bg-zinc-900'
                    : 'border-main bg-zinc-950 hover:border-alt'
                }`}
              >
                <div className="flex items-center gap-1.5 pr-6">
                  <Lock className="w-4 h-4 text-zinc-500 shrink-0" />
                  <span className="text-sm text-zinc-200 truncate">{v.name}</span>
                </div>
                <div className="text-xs text-zinc-500 mt-0.5">
                  {v.secret_count} secret{v.secret_count === 1 ? '' : 's'}
                </div>
              </button>
              <button
                type="button"
                onClick={() => removeVault(v)}
                disabled={vaultBusy === v.id}
                title="Delete vault"
                className="absolute top-2 right-2 p-1 text-zinc-600 hover:text-red-400 disabled:opacity-40"
              >
                {vaultBusy === v.id ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
                )}
              </button>
            </div>
          ))}

          <form
            onSubmit={createVaultSubmit}
            className="border border-main rounded-md bg-zinc-950 p-3 space-y-2"
          >
            <div className="text-xs font-medium text-zinc-400 flex items-center gap-1.5">
              <Plus className="w-4 h-4" /> Create vault
            </div>
            <TextInput id="vault-name" value={vaultName} onChange={setVaultName} placeholder="Name" />
            <TextInput
              id="vault-desc"
              value={vaultDesc}
              onChange={setVaultDesc}
              placeholder="Description (optional)"
            />
            <button
              type="submit"
              disabled={creatingVault || !vaultName.trim()}
              className="w-full bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors"
            >
              {creatingVault ? 'Creating…' : 'Create vault'}
            </button>
          </form>
        </div>

        {/* Right: selected vault's secrets */}
        <div className="space-y-4 min-w-0">
          {!selectedVault ? (
            <div className="rounded-md border border-main bg-zinc-950 p-6 text-sm text-zinc-500">
              Select a vault to view its secrets.
            </div>
          ) : (
            <>
              <div>
                <h3 className="text-sm font-semibold text-zinc-200">{selectedVault.name}</h3>
                {selectedVault.description && (
                  <p className="text-xs text-zinc-500 mt-0.5">{selectedVault.description}</p>
                )}
              </div>

              {secretsError && <p className="text-sm text-red-400">{secretsError}</p>}

              {secretsLoading ? (
                <div className="flex items-center gap-2 text-sm text-zinc-500">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading secrets…
                </div>
              ) : (
                <div className="space-y-3">
                  {secrets.length === 0 && (
                    <p className="text-sm text-zinc-500">No secrets in this vault yet.</p>
                  )}
                  {secrets.map((s) => {
                    const r = revealed[s.key]
                    const shown = Boolean(r && r.shown)
                    return (
                      <div
                        key={s.id ?? s.key}
                        className={`border border-main rounded-md bg-zinc-950 p-3 ${
                          s.expired ? 'opacity-50' : ''
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm text-zinc-200 truncate">{s.key}</span>
                          {s.expired && (
                            <span className="text-[10px] uppercase tracking-wide text-red-400 border border-red-400/30 rounded-full px-2 py-0.5">
                              expired
                            </span>
                          )}
                          <div className="ml-auto flex items-center gap-1">
                            <button
                              type="button"
                              onClick={() => toggleReveal(s.key)}
                              disabled={revealBusy === s.key}
                              title={shown ? 'Hide value' : 'Reveal value'}
                              className="p-2 text-zinc-400 hover:text-white border border-alt rounded-md disabled:opacity-40"
                            >
                              {revealBusy === s.key ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : shown ? (
                                <EyeOff className="w-4 h-4" />
                              ) : (
                                <Eye className="w-4 h-4" />
                              )}
                            </button>
                            {shown && <CopyButton text={r.value} title="Copy value" />}
                            <button
                              type="button"
                              onClick={() => removeSecret(s.key)}
                              disabled={secretBusy === s.key}
                              title="Delete secret"
                              className="p-2 text-zinc-400 hover:text-red-400 border border-alt rounded-md disabled:opacity-40"
                            >
                              {secretBusy === s.key ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <Trash2 className="w-4 h-4" />
                              )}
                            </button>
                          </div>
                        </div>
                        {s.description && (
                          <p className="text-xs text-zinc-500 mt-1">{s.description}</p>
                        )}
                        <code className="mt-2 block font-mono text-sm text-zinc-200 bg-black border border-alt rounded-md px-3 py-2 break-all">
                          {shown ? r.value : MASK}
                        </code>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Add / rotate secret */}
              <form
                onSubmit={addSecret}
                className="border border-main rounded-md bg-zinc-950 p-4 space-y-2"
              >
                <div className="text-xs font-medium text-zinc-400 flex items-center gap-1.5">
                  <Plus className="w-4 h-4" /> Add secret
                </div>
                <TextInput
                  id="secret-key"
                  value={secretKey}
                  onChange={setSecretKey}
                  placeholder="KEY_NAME"
                  className="font-mono"
                />
                <TextInput
                  id="secret-value"
                  type="password"
                  value={secretValue}
                  onChange={setSecretValue}
                  placeholder="Value"
                  className="font-mono"
                />
                <TextInput
                  id="secret-desc"
                  value={secretDesc}
                  onChange={setSecretDesc}
                  placeholder="Description (optional)"
                />
                <div className="flex items-center gap-3 pt-1">
                  <button
                    type="submit"
                    disabled={savingSecret || !secretKey.trim() || !secretValue}
                    className="bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors flex items-center gap-1.5"
                  >
                    {savingSecret && <Loader2 className="w-4 h-4 animate-spin" />}
                    {savingSecret ? 'Saving…' : 'Save secret'}
                  </button>
                  <span className="text-xs text-zinc-500">
                    Saving an existing key rotates its value.
                  </span>
                </div>
              </form>

              <p className="text-xs text-zinc-500 flex items-center gap-1.5">
                <Lock className="w-4 h-4 shrink-0" /> Values are Fernet-encrypted at rest and only
                decrypted when you reveal them.
              </p>
            </>
          )}
        </div>
      </div>
    </Pane>
  )
}
