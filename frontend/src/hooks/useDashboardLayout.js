import { useState, useCallback } from 'react'

// Ordered-list-with-visibility dashboard layout, ported from ServerKit's
// useDashboardLayout (plan 11). Deliberately not a 2-D drag grid: widgets are an ordered
// list of { id, label, visible }, persisted to localStorage and merged forward against
// DEFAULT_WIDGETS so a widget added in a later release shows up (visible) for users who
// already have a saved layout, without nuking their order.
const STORAGE_KEY = 'devicekit_dashboard_layout'

// The canonical widget set + default order. New widgets appended here ship visible-by-default
// and appear on upgrade for existing users (forward-merge below). Keyed to WIDGET_RENDERERS
// in Dashboard.jsx.
export const DEFAULT_WIDGETS = [
  { id: 'fleet-summary', label: 'Fleet Summary', visible: true },
  { id: 'fleet-health', label: 'Fleet Health', visible: true },
  { id: 'active-runs', label: 'Active Runs', visible: true },
  { id: 'recent-failures', label: 'Recent Failures', visible: true },
  { id: 'fql-bar', label: 'Fleet Query', visible: true },
  { id: 'device-registry', label: 'Device Registry', visible: true },
]

function loadWidgets() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY))
    if (!Array.isArray(stored)) return DEFAULT_WIDGETS.map(w => ({ ...w }))

    // Merge with defaults to handle widgets added in future versions.
    const storedMap = new Map(stored.map(w => [w.id, w]))
    const merged = []

    // Keep stored order for known widgets (drop ids no longer in DEFAULT_WIDGETS).
    for (const sw of stored) {
      const def = DEFAULT_WIDGETS.find(d => d.id === sw.id)
      if (def) merged.push({ ...def, visible: sw.visible })
    }

    // Append any new defaults not present in the stored layout.
    for (const dw of DEFAULT_WIDGETS) {
      if (!storedMap.has(dw.id)) merged.push({ ...dw })
    }

    return merged
  } catch {
    return DEFAULT_WIDGETS.map(w => ({ ...w }))
  }
}

function saveWidgets(widgets) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(widgets.map(({ id, visible }) => ({ id, visible }))))
}

export default function useDashboardLayout() {
  const [widgets, setWidgets] = useState(loadWidgets)

  const toggleWidget = useCallback((id) => {
    setWidgets(prev => {
      const next = prev.map(w => w.id === id ? { ...w, visible: !w.visible } : w)
      saveWidgets(next)
      return next
    })
  }, [])

  const moveWidget = useCallback((id, direction) => {
    setWidgets(prev => {
      const idx = prev.findIndex(w => w.id === id)
      if (idx < 0) return prev
      const swapIdx = direction === 'up' ? idx - 1 : idx + 1
      if (swapIdx < 0 || swapIdx >= prev.length) return prev
      const next = [...prev]
      ;[next[idx], next[swapIdx]] = [next[swapIdx], next[idx]]
      saveWidgets(next)
      return next
    })
  }, [])

  const resetLayout = useCallback(() => {
    const fresh = DEFAULT_WIDGETS.map(w => ({ ...w }))
    saveWidgets(fresh)
    setWidgets(fresh)
  }, [])

  const isVisible = useCallback((id) => {
    const w = widgets.find(w => w.id === id)
    return w ? w.visible : true
  }, [widgets])

  return { widgets, toggleWidget, moveWidget, resetLayout, isVisible }
}
