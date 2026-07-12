// White-label brand state (plan 28 part 3).
//
// An instance can override the brand *name* and *mark* (logo). Like accent + theme, the
// override is mirrored to localStorage so the sidebar/login/tab-title paint correctly on the
// first render (before /settings loads over HTTP); the Appearance pane reconciles the server's
// saved `appearance.brand_name` / `appearance.logo` over localStorage on load, so the brand
// follows the instance cross-browser. A window event lets Logo / sidebar / login re-render on
// change without threading a React context through the whole tree (Login renders pre-auth).
import { useEffect, useState } from 'react'

export const DEFAULT_BRAND_NAME = 'DeviceKit'
const LS_KEY = 'devicekit_brand'
const BRAND_EVENT = 'devicekit-brand-change'

export function getStoredBrand() {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return { brandName: '', logo: '' }
    const b = JSON.parse(raw) || {}
    return { brandName: b.brandName || '', logo: b.logo || '' }
  } catch {
    return { brandName: '', logo: '' }
  }
}

// The instance's display name — the override if set, else the DeviceKit default.
export function brandName(brand) {
  const b = brand || getStoredBrand()
  return b.brandName || DEFAULT_BRAND_NAME
}

// Persist a partial update ({ brandName?, logo? }) + notify subscribers. Storing first keeps
// the next reload's first paint correct.
export function setBrand(partial) {
  const next = { ...getStoredBrand(), ...partial }
  localStorage.setItem(LS_KEY, JSON.stringify(next))
  window.dispatchEvent(new CustomEvent(BRAND_EVENT, { detail: next }))
  return next
}

export function subscribeBrand(cb) {
  const on = () => cb(getStoredBrand())
  window.addEventListener(BRAND_EVENT, on)
  return () => window.removeEventListener(BRAND_EVENT, on)
}

// React hook: current brand, re-rendering when it changes (own edits + cross-tab is not
// covered, matching the accent/theme flow — the settings reconcile handles cross-browser).
export function useBrand() {
  const [brand, setBrandState] = useState(getStoredBrand)
  useEffect(() => subscribeBrand(setBrandState), [])
  return brand
}
