// Notification history view (plan 06.1).
//
// Full, filterable history of fleet notifications with severity badges, deep links to the
// subject, per-item mark-read / dismiss, and bulk mark-all / clear. Lives on the shared
// notifications store for the unread count + a live refetch signal (one SSE connection app-
// wide), and paginates its own list via `GET /notifications`. Modeled on Jobs.jsx.
import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bell,
  AlertCircle,
  AlertTriangle,
  Info,
  Check,
  CheckCheck,
  Trash2,
  Loader2,
  RefreshCw,
  ExternalLink,
  Settings2,
  SlidersHorizontal,
} from 'lucide-react'

import { api } from '../api'
import NotificationChannels from '../components/NotificationChannels'
import NotificationPreferences from '../components/NotificationPreferences'
import {
  useNotifications,
  markRead,
  markAllRead,
  removeNotification,
  refreshNotifications,
} from '../store/notifications'

const SEVERITY_FILTERS = [
  { key: '', label: 'All' },
  { key: 'unread', label: 'Unread' },
  { key: 'critical', label: 'Critical' },
  { key: 'warning', label: 'Warning' },
  { key: 'info', label: 'Info' },
]

const SEVERITY_STYLE = {
  critical: 'bg-red-500/10 text-red-400',
  warning: 'bg-amber-500/10 text-amber-400',
  info: 'bg-blue-500/10 text-blue-400',
}
const SEVERITY_ICON = { critical: AlertCircle, warning: AlertTriangle, info: Info }

function fmtTime(epoch) {
  if (!epoch) return '--'
  return new Date(Number(epoch) * 1000).toLocaleString()
}

function SeverityBadge({ severity }) {
  const Icon = SEVERITY_ICON[severity] || Info
  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
        SEVERITY_STYLE[severity] || SEVERITY_STYLE.info
      }`}
    >
      <Icon className="w-3 h-3" />
      {severity}
    </span>
  )
}

export default function Notifications() {
  const { unread } = useNotifications()
  const [filter, setFilter] = useState('')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [showChannels, setShowChannels] = useState(false)
  const [showPrefs, setShowPrefs] = useState(false)
  const navigate = useNavigate()

  const fetchItems = useCallback(async () => {
    try {
      const params = { limit: 100 }
      if (filter === 'unread') params.unread = 'true'
      else if (filter) params.severity = filter
      const res = await api.getNotifications(params)
      setItems(res.notifications || [])
    } catch {
      /* keep current state on transient errors */
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    fetchItems()
  }, [fetchItems])

  // Re-fetch when the store's unread count changes (a new SSE notification arrived, or a
  // mark-read reconciled) so the list stays live without its own EventSource.
  useEffect(() => {
    fetchItems()
  }, [unread, fetchItems])

  const openItem = (n) => {
    if (!n.read) markRead(n.id, true)
    if (n.deep_link) navigate(n.deep_link)
  }

  const clearAll = async () => {
    if (!window.confirm('Delete all notifications? This cannot be undone.')) return
    await api.clearNotifications()
    refreshNotifications()
    fetchItems()
  }

  return (
    <div className="flex-1 overflow-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bell className="w-5 h-5 text-emerald-400" />
          <div>
            <h1 className="text-xl font-bold">Notifications</h1>
            <p className="text-xs text-zinc-500">
              Fleet events — device health, automation runs, regressions
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPrefs((v) => !v)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border ${
              showPrefs
                ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400'
                : 'border-main text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" /> Preferences
          </button>
          <button
            onClick={() => setShowChannels((v) => !v)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border ${
              showChannels
                ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400'
                : 'border-main text-zinc-400 hover:text-zinc-200'
            }`}
          >
            <Settings2 className="w-3.5 h-3.5" /> Channels
          </button>
          <button
            onClick={() => markAllRead()}
            disabled={unread === 0}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-main text-zinc-400 hover:text-emerald-400 disabled:opacity-40 disabled:hover:text-zinc-400"
          >
            <CheckCheck className="w-3.5 h-3.5" /> Mark all read
          </button>
          <button
            onClick={clearAll}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-main text-zinc-400 hover:text-red-400"
          >
            <Trash2 className="w-3.5 h-3.5" /> Clear all
          </button>
          <button
            onClick={() => { setLoading(true); fetchItems() }}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-main text-zinc-400 hover:text-zinc-200"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>
      </div>

      {/* Preferences */}
      {showPrefs && (
        <div className="border border-main rounded-lg p-4 bg-zinc-900/40 space-y-3">
          <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">
            Preferences
          </p>
          <NotificationPreferences />
        </div>
      )}

      {/* Delivery channels config */}
      {showChannels && (
        <div className="border border-main rounded-lg p-4 bg-zinc-900/40 space-y-3">
          <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">
            Delivery channels
          </p>
          <NotificationChannels />
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-2">
        {SEVERITY_FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`text-xs px-3 py-1.5 rounded border ${
              filter === f.key
                ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400'
                : 'border-main text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {f.label}
            {f.key === 'unread' && unread > 0 ? ` (${unread})` : ''}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="bg-zinc-900 border border-main rounded-lg overflow-hidden">
        {loading ? (
          <div className="px-4 py-10 text-center text-zinc-500">
            <Loader2 className="w-4 h-4 animate-spin inline" /> Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="px-4 py-12 text-center text-zinc-500">
            <Bell className="w-6 h-6 mx-auto mb-2 opacity-40" />
            No notifications
          </div>
        ) : (
          items.map((n) => (
            <div
              key={n.id}
              className={`group flex items-start gap-3 px-4 py-3 border-b border-main last:border-0 hover:bg-zinc-800/50 ${
                n.read ? 'opacity-60' : ''
              }`}
            >
              {!n.read && <span className="mt-2 w-2 h-2 rounded-full bg-emerald-500 shrink-0" />}
              {n.read && <span className="mt-2 w-2 h-2 shrink-0" />}
              <div
                className="flex-1 min-w-0 cursor-pointer"
                onClick={() => openItem(n)}
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <SeverityBadge severity={n.severity} />
                  <span className="text-sm font-medium text-zinc-100">{n.title}</span>
                  {n.deep_link && (
                    <ExternalLink className="w-3 h-3 text-zinc-600 group-hover:text-emerald-400" />
                  )}
                </div>
                {n.body && <p className="text-xs text-zinc-500 mt-1">{n.body}</p>}
                <p className="text-[10px] text-zinc-600 mt-1 mono">
                  {n.category} · {n.event_key} · {fmtTime(n.created_at)}
                </p>
              </div>
              <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                {!n.read && (
                  <button
                    onClick={() => markRead(n.id, true)}
                    title="Mark read"
                    className="text-zinc-500 hover:text-emerald-400"
                  >
                    <Check className="w-4 h-4" />
                  </button>
                )}
                <button
                  onClick={() => removeNotification(n.id)}
                  title="Dismiss"
                  className="text-zinc-500 hover:text-red-400"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
