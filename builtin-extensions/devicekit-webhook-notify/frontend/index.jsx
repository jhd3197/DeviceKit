// Webhook Notifier — builtin extension frontend (plan 04).
//
// This module is the SOURCE OF TRUTH. It is synced verbatim into
// `frontend/src/extensions/devicekit-webhook-notify/index.jsx` by
// `scripts/sync-builtin-frontends.mjs` (CI enforces no drift). Do not edit the copy.
//
// Extensions import shared host code ONLY from the stable `devicekit-sdk` alias — never
// from `../../` internals. Named exports here match the `component` strings the manifest's
// `contributions` block references (WebhookNotifyPage, WebhookNotifyWidget). A `contributions`
// export mirrors the manifest so the app can render this builtin from the build-time glob
// even when the contributions endpoint is briefly unavailable.
import React, { useEffect, useState } from 'react'
import { api, Link } from 'devicekit-sdk'

export const contributions = {
  nav: [
    {
      id: 'webhook-notify',
      label: 'Webhook Notify',
      route: '/x/webhook-notify',
      section: 'Extensions',
    },
  ],
  routes: [{ path: '/x/webhook-notify', component: 'WebhookNotifyPage' }],
  widgets: [{ slot: 'dashboard.top', component: 'WebhookNotifyWidget' }],
  page_titles: { '/x/webhook-notify': 'Webhook Notify' },
}

const SLUG = 'devicekit-webhook-notify'

/** Full page mounted at /x/webhook-notify. Reads + saves this extension's config through
 *  the same REST surface the marketplace uses, proving an extension page needs no host edits. */
export function WebhookNotifyPage() {
  const [config, setConfig] = useState(null)
  const [message, setMessage] = useState('')
  const [status, setStatus] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getExtensionConfig(SLUG)
      .then((r) => {
        setConfig(r.config || {})
        setMessage(r.config?.default_message || '')
      })
      .catch(() => setConfig({}))
  }, [])

  const save = async () => {
    setSaving(true)
    setStatus(null)
    try {
      await api.updateExtensionConfig(SLUG, { default_message: message })
      setStatus({ ok: true, text: 'Saved.' })
    } catch (e) {
      setStatus({ ok: false, text: e.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <header className="h-14 border-b border-main flex items-center px-8 bg-black/50 backdrop-blur-md shrink-0">
        <span className="text-sm font-semibold text-zinc-200">Webhook Notify</span>
        <span className="ml-3 text-[10px] mono uppercase tracking-widest text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-2 py-0.5">
          Extension
        </span>
      </header>

      <div className="flex-1 overflow-y-auto p-8 max-w-2xl space-y-6">
        <p className="text-sm text-zinc-400">
          Send fleet notifications to a Slack/Discord-compatible webhook. Configure the
          webhook URL in the marketplace; set a default message body here.
        </p>

        <div className="bg-card border border-main rounded-lg p-5 space-y-3">
          <label className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
            Default message
          </label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={3}
            placeholder="Fleet alert: {message}"
            className="w-full bg-body border border-main rounded px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-border-alt resize-none"
          />
          <div className="flex items-center gap-3">
            <button
              onClick={save}
              disabled={saving || config === null}
              className="px-3 py-1.5 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white transition-colors"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            {status && (
              <span className={`text-xs ${status.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                {status.text}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/** Compact widget mounted into the `dashboard.top` slot. Reads the extension config and
 *  reports the real state: active only when a webhook URL is actually configured (the API
 *  masks the secret but presence is still detectable). Renders nothing while loading. */
export function WebhookNotifyWidget() {
  const [configured, setConfigured] = useState(null) // null = loading

  useEffect(() => {
    api.getExtensionConfig(SLUG)
      .then((r) => setConfigured(!!r.config?.webhook_url))
      .catch(() => setConfigured(false))
  }, [])

  if (configured === null) return null

  if (!configured) {
    return (
      <div className="bg-card border border-main rounded-lg p-4 flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-zinc-600 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-zinc-400">Webhook alerts off</p>
          <p className="text-[10px] text-zinc-600 truncate">No webhook URL configured.</p>
        </div>
        <Link
          to="/extensions"
          className="text-[10px] font-semibold text-emerald-400 hover:text-emerald-300 shrink-0"
        >
          Set up
        </Link>
      </div>
    )
  }

  return (
    <div className="bg-card border border-main rounded-lg p-4 flex items-center gap-3">
      <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold text-zinc-200">Webhook alerts active</p>
        <p className="text-[10px] text-zinc-500 truncate">
          Fleet alerts are delivered to your webhook.
        </p>
      </div>
    </div>
  )
}
