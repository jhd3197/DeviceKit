// Notification bus store (plan 06).
//
// One singleton opens a single SSE connection (`onNotification`) and keeps the unread count
// + a rolling list of recent notifications for the sidebar bell. Components subscribe via
// `useNotifications()` (useSyncExternalStore) — the same store idiom as `contributions.js`,
// so the whole app shares one connection instead of each view opening its own EventSource.
//
// Mutations are optimistic (mark-read flips local state immediately) and reconciled by a
// refetch, matching the ServerKit NotificationsContext behavior described in the plan.
import { useSyncExternalStore } from 'react'
import { api, subscribeToEvents } from '../api'

const RECENT_LIMIT = 30

let state = { recent: [], unread: 0, connected: false, loading: true }
const listeners = new Set()
let started = false
let es = null

function setState(next) {
  state = { ...state, ...next }
  for (const cb of listeners) cb()
}

/** Full refetch — the source of truth that reconciles any optimistic drift. */
export async function refreshNotifications() {
  try {
    const res = await api.getNotifications({ limit: RECENT_LIMIT })
    setState({
      recent: res.notifications || [],
      unread: res.unread ?? 0,
      loading: false,
    })
  } catch {
    setState({ loading: false })
  }
  return state
}

function onIncoming(notif) {
  // Prepend, de-dupe by id, cap the list, and bump unread.
  const recent = [notif, ...state.recent.filter((n) => n.id !== notif.id)].slice(0, RECENT_LIMIT)
  setState({ recent, unread: state.unread + (notif.read ? 0 : 1) })
}

function ensureStream() {
  if (es) return
  es = subscribeToEvents({
    onNotification: (n) => onIncoming(n),
    onError: () => setState({ connected: false }),
  })
  // EventSource emits a bare `connected` event on open (see api.js SSE contract).
  es.addEventListener('connected', () => setState({ connected: true }))
  es.addEventListener('open', () => setState({ connected: true }))
}

// --- optimistic mutations -------------------------------------------------
export async function markRead(id, read = true) {
  const target = state.recent.find((n) => n.id === id)
  if (target && !!target.read !== read) {
    setState({
      recent: state.recent.map((n) => (n.id === id ? { ...n, read } : n)),
      unread: Math.max(0, state.unread + (read ? -1 : 1)),
    })
  }
  try {
    await api.markNotificationRead(id, read)
  } finally {
    refreshNotifications()
  }
}

export async function markAllRead() {
  setState({ recent: state.recent.map((n) => ({ ...n, read: true })), unread: 0 })
  try {
    await api.markAllNotificationsRead()
  } finally {
    refreshNotifications()
  }
}

export async function removeNotification(id) {
  const target = state.recent.find((n) => n.id === id)
  setState({
    recent: state.recent.filter((n) => n.id !== id),
    unread: Math.max(0, state.unread - (target && !target.read ? 1 : 0)),
  })
  try {
    await api.deleteNotification(id)
  } finally {
    refreshNotifications()
  }
}

function subscribe(cb) {
  if (!started) {
    started = true
    ensureStream()
    refreshNotifications()
  }
  listeners.add(cb)
  return () => listeners.delete(cb)
}

function getSnapshot() {
  return state
}

/** React hook: `{ recent, unread, connected, loading }`. */
export function useNotifications() {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}
