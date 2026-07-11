// Per-pane form state for Settings panes (plan 12).
//
// Seeds a local draft from the given keys of the shared settings object, tracks whether the
// draft diverges from what's saved, and persists just the changed keys through the shell's
// `save`. Panes stay declarative: read `draft`, call `set(key, value)`, render a <SaveBar>.
import { useCallback, useMemo, useState } from 'react'

function pick(obj, keys) {
  const out = {}
  for (const k of keys) out[k] = obj?.[k]
  return out
}

export function usePaneForm(settings, keys, save) {
  const saved = useMemo(() => pick(settings, keys), [settings, keys])
  const [draft, setDraft] = useState(saved)
  const [baseline, setBaseline] = useState(saved)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState(null)
  const [error, setError] = useState(null)

  // Re-seed when the upstream settings object identity changes (initial load / external
  // update) but the user hasn't started editing this pane.
  if (saved !== baseline && !saving) {
    // Only adopt upstream if the draft still matches the old baseline (no local edits).
    const dirtyNow = keys.some((k) => draft[k] !== baseline[k])
    if (!dirtyNow) {
      setBaseline(saved)
      setDraft(saved)
    }
  }

  const dirty = keys.some((k) => draft[k] !== baseline[k])

  const set = useCallback((key, value) => {
    setDraft((d) => ({ ...d, [key]: value }))
    setSavedAt(null)
    setError(null)
  }, [])

  const reset = useCallback(() => {
    setDraft(baseline)
    setError(null)
  }, [baseline])

  const persist = useCallback(async () => {
    setSaving(true)
    setError(null)
    try {
      const patch = {}
      for (const k of keys) if (draft[k] !== baseline[k]) patch[k] = draft[k]
      await save(patch)
      setBaseline(draft)
      setSavedAt(Date.now())
    } catch (e) {
      setError(e.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }, [draft, baseline, keys, save])

  return { draft, set, dirty, saving, savedAt, error, reset, persist }
}
