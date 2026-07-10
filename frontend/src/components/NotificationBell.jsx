// Sidebar notification bell (plan 06.1).
//
// Unread badge fed by the shared notifications store (single SSE connection). Clicking opens
// a dropdown of recent notifications with severity dots and deep links; clicking an item marks
// it read and navigates to its subject. "Mark all read" and "View all" (→ /notifications) live
// in the footer. Closes on outside click, matching the Dashboard dropdown idiom.
import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, Check, CheckCheck, X } from 'lucide-react'

import { useNotifications, markRead, markAllRead, removeNotification } from '../store/notifications'

const SEVERITY_DOT = {
  critical: 'bg-red-500',
  warning: 'bg-amber-500',
  info: 'bg-blue-500',
}

function timeAgo(ts) {
  if (!ts) return ''
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export default function NotificationBell() {
  const { recent, unread, connected } = useNotifications()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const openItem = (n) => {
    if (!n.read) markRead(n.id, true)
    setOpen(false)
    if (n.deep_link) navigate(n.deep_link)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        title="Notifications"
        className="relative w-8 h-8 flex items-center justify-center rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition-colors"
      >
        <Bell className="w-4 h-4" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-red-500 text-white text-[9px] font-bold leading-none">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
        {!connected && (
          <span className="absolute bottom-0 right-0 w-1.5 h-1.5 rounded-full bg-amber-500" title="Reconnecting" />
        )}
      </button>

      {open && (
        <div className="absolute top-full right-0 mt-2 w-80 bg-zinc-900 border border-main rounded-lg shadow-xl z-50 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-main">
            <span className="text-xs font-bold text-zinc-200 uppercase tracking-widest">
              Notifications
            </span>
            {unread > 0 && (
              <button
                onClick={() => markAllRead()}
                className="flex items-center gap-1 text-[10px] text-zinc-400 hover:text-emerald-400"
              >
                <CheckCheck className="w-3 h-3" /> Mark all read
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {recent.length === 0 ? (
              <div className="px-4 py-8 text-center text-xs text-zinc-500">
                <Bell className="w-5 h-5 mx-auto mb-2 opacity-40" />
                No notifications yet
              </div>
            ) : (
              recent.map((n) => (
                <div
                  key={n.id}
                  className={`group flex items-start gap-2 px-3 py-2.5 border-b border-main last:border-0 cursor-pointer hover:bg-zinc-800 ${
                    n.read ? 'opacity-60' : ''
                  }`}
                  onClick={() => openItem(n)}
                >
                  <span
                    className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${
                      SEVERITY_DOT[n.severity] || SEVERITY_DOT.info
                    }`}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-zinc-100 truncate">{n.title}</p>
                    {n.body && (
                      <p className="text-[11px] text-zinc-500 line-clamp-2">{n.body}</p>
                    )}
                    <p className="text-[10px] text-zinc-600 mt-0.5">{timeAgo(n.created_at)}</p>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {!n.read && (
                      <button
                        onClick={(e) => { e.stopPropagation(); markRead(n.id, true) }}
                        title="Mark read"
                        className="text-zinc-500 hover:text-emerald-400"
                      >
                        <Check className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); removeNotification(n.id) }}
                      title="Dismiss"
                      className="text-zinc-500 hover:text-red-400"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          <button
            onClick={() => { setOpen(false); navigate('/notifications') }}
            className="w-full px-3 py-2 text-center text-[11px] text-zinc-400 hover:text-white hover:bg-zinc-800 border-t border-main"
          >
            View all notifications
          </button>
        </div>
      )}
    </div>
  )
}
