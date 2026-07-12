// Settings deep-link focus (plan 26, ported from ServerKit's hooks/useSettingFocus.js).
//
// The command palette's settings omnisearch deep-links to `/settings/<tab>?focus=setting:<id>`.
// This hook is called once by the Settings shell; it reads the `focus` query param and hands each
// pane a `register(id)` it spreads onto the card/field container it owns. When the focused card
// mounts (or the focus id changes to an already-mounted card), the hook scrolls it into view and
// applies a ~2 s `.is-setting-focused` flash so the user's eye lands on the right control.
import { useCallback, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'

const FLASH_MS = 2000

// Parse `?focus=setting:<id>` → `<id>` (or null). Exported for the palette/tests.
export function focusIdFromSearch(search) {
  const raw = new URLSearchParams(search || '').get('focus') || ''
  const m = raw.match(/^setting:(.+)$/)
  return m ? m[1] : null
}

export function useSettingFocus() {
  const location = useLocation()
  const focusId = focusIdFromSearch(location.search)
  const nodes = useRef(new Map()) // id → DOM node, kept live via ref callbacks
  const flashedFor = useRef(null) // last focus id we've already flashed (avoid re-flashing)

  const flash = useCallback((node) => {
    if (!node) return
    node.scrollIntoView({ behavior: 'smooth', block: 'center' })
    // Restart the keyframe if the class is already present.
    node.classList.remove('is-setting-focused')
    void node.offsetWidth // force reflow
    node.classList.add('is-setting-focused')
    setTimeout(() => node.classList.remove('is-setting-focused'), FLASH_MS)
  }, [])

  // register(id) → props for a card/field container. The ref callback records the node and, when
  // it is the current focus target and hasn't been flashed yet, scrolls + flashes it next frame.
  const register = useCallback(
    (id) => ({
      'data-setting-id': id,
      ref: (node) => {
        if (node) nodes.current.set(id, node)
        else nodes.current.delete(id)
        if (node && id === focusId && flashedFor.current !== focusId) {
          flashedFor.current = focusId
          requestAnimationFrame(() => flash(node))
        }
      },
    }),
    [focusId, flash]
  )

  // Handle the case where the target is already mounted when the focus id changes (e.g. deep-link
  // to a card in the pane you're already on). Reset the guard when focus clears.
  useEffect(() => {
    if (!focusId) {
      flashedFor.current = null
      return
    }
    const node = nodes.current.get(focusId)
    if (node && flashedFor.current !== focusId) {
      flashedFor.current = focusId
      requestAnimationFrame(() => flash(node))
    }
  }, [focusId, flash])

  return { focusId, register }
}
