// Notification delivery-channel config (plan 06.2/06.3).
//
// A card per async channel (webhook now; email in 06.3) with a schema-driven form. Secrets
// come back masked (••••••) and are only re-sent when the operator types a new value, so the
// form round-trips without leaking. "Test" fires a synchronous sample delivery for instant
// feedback; "Save" persists enabled + config.
import React, { useEffect, useState } from 'react'
import { Webhook, Mail, Send, Loader2, CheckCircle, XCircle } from 'lucide-react'

import { api } from '../api'

const CHANNEL_META = {
  webhook: {
    label: 'Webhook',
    icon: Webhook,
    hint: 'Slack / Discord-compatible incoming webhook.',
    fields: [
      { key: 'url', label: 'Webhook URL', type: 'password', placeholder: 'https://hooks.slack.com/services/…' },
      { key: 'format', label: 'Format', type: 'select', options: ['slack', 'discord', 'generic'] },
      { key: 'min_severity', label: 'Minimum severity', type: 'select', options: ['info', 'warning', 'critical'] },
    ],
  },
  email: {
    label: 'Email',
    icon: Mail,
    hint: 'SMTP delivery. Credentials are encrypted at rest.',
    fields: [
      { key: 'smtp_host', label: 'SMTP host', type: 'text', placeholder: 'smtp.example.com' },
      { key: 'smtp_port', label: 'Port', type: 'number', placeholder: '587' },
      { key: 'smtp_user', label: 'Username', type: 'text' },
      { key: 'smtp_password', label: 'Password', type: 'password' },
      { key: 'from_addr', label: 'From address', type: 'text' },
      { key: 'to_addrs', label: 'To (comma-separated)', type: 'text' },
      { key: 'min_severity', label: 'Minimum severity', type: 'select', options: ['info', 'warning', 'critical'] },
    ],
  },
}

function ChannelCard({ data, onChanged }) {
  const meta = CHANNEL_META[data.channel]
  const [enabled, setEnabled] = useState(data.enabled)
  const [config, setConfig] = useState(data.config || {})
  const [dirtySecrets, setDirtySecrets] = useState({})
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const secretKeys = new Set(data.secret_keys || [])

  if (!meta) return null
  const Icon = meta.icon

  const setField = (key, value) => {
    setConfig((c) => ({ ...c, [key]: value }))
    if (secretKeys.has(key)) setDirtySecrets((d) => ({ ...d, [key]: true }))
  }

  const buildPayloadConfig = () => {
    // Omit masked secrets the operator didn't touch so the backend keeps the stored value.
    const out = {}
    for (const f of meta.fields) {
      const v = config[f.key]
      if (secretKeys.has(f.key) && !dirtySecrets[f.key]) continue
      out[f.key] = v
    }
    return out
  }

  const save = async () => {
    setBusy(true); setStatus(null)
    try {
      await api.updateNotificationChannel(data.channel, {
        enabled,
        config: buildPayloadConfig(),
      })
      setStatus({ ok: true, text: 'Saved.' })
      setDirtySecrets({})
      onChanged?.()
    } catch (e) {
      setStatus({ ok: false, text: e.message })
    } finally {
      setBusy(false)
    }
  }

  const test = async () => {
    setBusy(true); setStatus(null)
    try {
      await api.testNotificationChannel(data.channel)
      setStatus({ ok: true, text: 'Test delivered.' })
    } catch (e) {
      setStatus({ ok: false, text: e.message || 'Test failed' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-card border border-main rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-emerald-400" />
          <div>
            <p className="text-sm font-semibold text-zinc-100">{meta.label}</p>
            <p className="text-[11px] text-zinc-500">{meta.hint}</p>
          </div>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="rounded border-zinc-600 bg-black text-emerald-500 focus:ring-emerald-500 focus:ring-offset-0"
          />
          <span className="text-xs text-zinc-400">Enabled</span>
        </label>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {meta.fields.map((f) => (
          <div key={f.key} className={f.type === 'password' || f.key === 'to_addrs' ? 'sm:col-span-2' : ''}>
            <label className="block text-[10px] font-semibold uppercase tracking-widest text-zinc-500 mb-1">
              {f.label}
            </label>
            {f.type === 'select' ? (
              <select
                value={config[f.key] ?? f.options[0]}
                onChange={(e) => setField(f.key, e.target.value)}
                className="w-full bg-black border border-main rounded px-2 py-1.5 text-xs text-zinc-200 focus:border-alt outline-none"
              >
                {f.options.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            ) : (
              <input
                type={f.type === 'password' ? 'password' : f.type === 'number' ? 'number' : 'text'}
                value={config[f.key] ?? ''}
                placeholder={f.placeholder || ''}
                onChange={(e) => setField(f.key, e.target.value)}
                className="w-full bg-black border border-main rounded px-2 py-1.5 text-xs text-zinc-200 mono focus:border-alt outline-none"
              />
            )}
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={save}
          disabled={busy}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null} Save
        </button>
        <button
          onClick={test}
          disabled={busy || !enabled}
          title={enabled ? 'Send a test notification' : 'Enable and save first'}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-main text-zinc-300 hover:text-white disabled:opacity-40"
        >
          <Send className="w-3.5 h-3.5" /> Test
        </button>
        {status && (
          <span className={`flex items-center gap-1 text-xs ${status.ok ? 'text-emerald-400' : 'text-red-400'}`}>
            {status.ok ? <CheckCircle className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
            {status.text}
          </span>
        )}
      </div>
    </div>
  )
}

export default function NotificationChannels() {
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    api.getNotificationChannels()
      .then((r) => setChannels(r.channels || []))
      .catch(() => setChannels([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  if (loading) {
    return (
      <div className="text-xs text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin inline" /> Loading channels…
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {channels.map((c) => (
        <ChannelCard key={c.channel} data={c} onChanged={load} />
      ))}
    </div>
  )
}
