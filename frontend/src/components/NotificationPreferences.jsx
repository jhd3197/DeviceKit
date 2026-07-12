// Notification preferences (plan 06.3): quiet hours, digest batching, per-event mutes.
//
// Quiet hours + digest settings save as one PUT; per-event mute toggles apply immediately
// (a full mute — no channel — drops the event across every channel, in-app included).
import React, { useEffect, useState } from 'react'
import { Moon, Layers, BellOff, Loader2, CheckCircle, XCircle } from 'lucide-react'

import { api } from '../api'

const HOURS = Array.from({ length: 24 }, (_, i) => i)

export default function NotificationPreferences() {
  const [settings, setSettings] = useState(null)
  const [events, setEvents] = useState([])
  const [muted, setMuted] = useState(new Set())
  const [status, setStatus] = useState(null)
  const [saving, setSaving] = useState(false)

  const load = () => {
    Promise.all([api.getNotificationPreferences(), api.getNotificationEvents()])
      .then(([prefs, ev]) => {
        setSettings(prefs.settings)
        setMuted(new Set((prefs.mutes || []).filter((m) => !m.channel).map((m) => m.event_key)))
        setEvents(ev.events || [])
      })
      .catch(() => setSettings({}))
  }
  useEffect(load, [])

  if (!settings) {
    return (
      <div className="text-xs text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin inline" /> Loading preferences…
      </div>
    )
  }

  const set = (k, v) => setSettings((s) => ({ ...s, [k]: v }))

  const toggleDigestEvent = (key) => {
    const list = new Set(settings.digest_events || [])
    list.has(key) ? list.delete(key) : list.add(key)
    set('digest_events', [...list])
  }

  const save = async () => {
    setSaving(true); setStatus(null)
    try {
      await api.updateNotificationPreferences({
        quiet_hours_enabled: settings.quiet_hours_enabled,
        quiet_start: Number(settings.quiet_start),
        quiet_end: Number(settings.quiet_end),
        quiet_allow_critical: settings.quiet_allow_critical,
        digest_enabled: settings.digest_enabled,
        digest_window_minutes: Number(settings.digest_window_minutes),
        digest_events: settings.digest_events || [],
      })
      setStatus({ ok: true, text: 'Saved.' })
    } catch (e) {
      setStatus({ ok: false, text: e.message })
    } finally {
      setSaving(false)
    }
  }

  const toggleMute = async (key) => {
    const next = new Set(muted)
    const willMute = !next.has(key)
    willMute ? next.add(key) : next.delete(key)
    setMuted(next)
    try {
      await api.setNotificationMute({ event_key: key, muted: willMute })
    } catch {
      load() // reconcile on failure
    }
  }

  return (
    <div className="space-y-4">
      {/* Quiet hours */}
      <div className="bg-card border border-main rounded-lg p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Moon className="w-4 h-4 text-blue-400" />
          <p className="text-sm font-semibold text-zinc-100">Quiet hours</p>
        </div>
        <p className="text-[11px] text-zinc-500">
          Suppress webhook / email delivery during this daily window. In-app history is kept.
        </p>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={settings.quiet_hours_enabled}
            onChange={(e) => set('quiet_hours_enabled', e.target.checked)}
            className="rounded border-zinc-600 bg-body text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
          />
          <span className="text-xs text-zinc-400">Enable quiet hours</span>
        </label>
        <div className="flex items-center gap-3 flex-wrap">
          <label className="text-xs text-zinc-400 flex items-center gap-1.5">
            From
            <select
              value={settings.quiet_start}
              onChange={(e) => set('quiet_start', e.target.value)}
              className="bg-body border border-main rounded px-2 py-1 text-xs mono"
            >
              {HOURS.map((h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
            </select>
          </label>
          <label className="text-xs text-zinc-400 flex items-center gap-1.5">
            To
            <select
              value={settings.quiet_end}
              onChange={(e) => set('quiet_end', e.target.value)}
              className="bg-body border border-main rounded px-2 py-1 text-xs mono"
            >
              {HOURS.map((h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.quiet_allow_critical}
              onChange={(e) => set('quiet_allow_critical', e.target.checked)}
              className="rounded border-zinc-600 bg-body text-red-500 focus:ring-red-500 focus:ring-offset-0"
            />
            <span className="text-xs text-zinc-400">Let critical alerts through</span>
          </label>
        </div>
      </div>

      {/* Digest */}
      <div className="bg-card border border-main rounded-lg p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-amber-400" />
          <p className="text-sm font-semibold text-zinc-100">Digest batching</p>
        </div>
        <p className="text-[11px] text-zinc-500">
          Batch noisy events into one periodic summary instead of a push per event.
        </p>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={settings.digest_enabled}
            onChange={(e) => set('digest_enabled', e.target.checked)}
            className="rounded border-zinc-600 bg-body text-amber-500 focus:ring-amber-500 focus:ring-offset-0"
          />
          <span className="text-xs text-zinc-400">Enable digests</span>
        </label>
        <label className="text-xs text-zinc-400 flex items-center gap-1.5">
          Flush window
          <input
            type="number"
            min="1"
            value={settings.digest_window_minutes}
            onChange={(e) => set('digest_window_minutes', e.target.value)}
            className="w-16 bg-body border border-main rounded px-2 py-1 text-xs mono"
          />
          minutes
        </label>
        {settings.digest_enabled && (
          <div className="pt-1">
            <p className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1.5">
              Events to batch
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {events.map((ev) => (
                <label key={ev.event_key} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={(settings.digest_events || []).includes(ev.event_key)}
                    onChange={() => toggleDigestEvent(ev.event_key)}
                    className="rounded border-zinc-600 bg-body text-amber-500 focus:ring-amber-500 focus:ring-offset-0"
                  />
                  <span className="text-[11px] text-zinc-400 mono truncate">{ev.event_key}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null} Save preferences
        </button>
        {status && (
          <span className={`flex items-center gap-1 text-xs ${status.ok ? 'text-emerald-400' : 'text-red-400'}`}>
            {status.ok ? <CheckCircle className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
            {status.text}
          </span>
        )}
      </div>

      {/* Per-event mutes */}
      <div className="bg-card border border-main rounded-lg p-4 space-y-2">
        <div className="flex items-center gap-2">
          <BellOff className="w-4 h-4 text-zinc-400" />
          <p className="text-sm font-semibold text-zinc-100">Muted events</p>
        </div>
        <p className="text-[11px] text-zinc-500">
          A muted event is dropped entirely — no bell, no webhook, no email.
        </p>
        <div className="divide-y divide-zinc-800">
          {events.map((ev) => (
            <div key={ev.event_key} className="flex items-center justify-between py-2">
              <div className="min-w-0">
                <p className="text-xs text-zinc-200 truncate">{ev.title}</p>
                <p className="text-[10px] text-zinc-600 mono">{ev.event_key}</p>
              </div>
              <button
                onClick={() => toggleMute(ev.event_key)}
                className={`text-[10px] px-2 py-1 rounded border shrink-0 ${
                  muted.has(ev.event_key)
                    ? 'border-red-500/40 bg-red-500/10 text-red-400'
                    : 'border-main text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {muted.has(ev.event_key) ? 'Muted' : 'Mute'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
