// Contribution envelope store (plan 04, port of ServerKit's contributions.js).
//
// One singleton fetches `GET /extensions/contributions` (the merged declarative UI of every
// active extension), caches it, and notifies subscribers via useSyncExternalStore. The app
// re-fetches through `refreshContributions()` after any install / enable / disable so nav,
// routes, and widgets update without a reload.
//
// Component code for BUILTIN extensions is compiled into the app bundle via a build-time
// glob (third-party extensions contribute backend only — see ADR/plan). `resolveComponent`
// maps a manifest `component` string to the extension module's named export. If the
// endpoint is briefly unavailable, we fall back to an envelope derived from the globbed
// builtins' own `contributions` exports so they still render.
import { useSyncExternalStore } from 'react'
import { api } from '../api'

// Eager glob: every builtin frontend is `src/extensions/<slug>/index.jsx` exporting its
// components (and a `contributions` mirror for the offline fallback).
const modules = import.meta.glob('./*/index.jsx', { eager: true })

function emptyEnvelope() {
  return {
    nav: [],
    routes: [],
    widgets: [],
    command_palette: [],
    page_titles: {},
    sdk_version: null,
  }
}

function slugFromKey(key) {
  const m = key.match(/^\.\/([^/]+)\/index\.jsx$/)
  return m ? m[1] : null
}

/** Resolve a manifest `component` string to the extension module's named export.
 *  Returns null (never throws) if the module or export is missing — the caller renders a
 *  dev warning and skips it rather than white-screening. */
export function resolveComponent(slug, name) {
  const mod = modules[`./${slug}/index.jsx`]
  if (!mod) {
    // eslint-disable-next-line no-console
    console.warn(`[extensions] no frontend module bundled for '${slug}' (component '${name}')`)
    return null
  }
  const Comp = mod[name]
  if (!Comp) {
    // eslint-disable-next-line no-console
    console.warn(`[extensions] '${slug}' has no exported component '${name}'`)
    return null
  }
  return Comp
}

/** Build an envelope from the globbed builtins' exported `contributions` (offline fallback). */
function builtinEnvelope() {
  const env = emptyEnvelope()
  for (const [key, mod] of Object.entries(modules)) {
    const slug = slugFromKey(key)
    const c = mod?.contributions
    if (!slug || !c) continue
    for (const kind of ['nav', 'routes', 'widgets', 'command_palette']) {
      for (const entry of c[kind] || []) env[kind].push({ ...entry, slug })
    }
    Object.assign(env.page_titles, c.page_titles || {})
  }
  return env
}

function normalize(env) {
  const base = emptyEnvelope()
  return {
    ...base,
    ...env,
    nav: env.nav || [],
    routes: env.routes || [],
    widgets: env.widgets || [],
    command_palette: env.command_palette || [],
    page_titles: env.page_titles || {},
  }
}

let state = { envelope: emptyEnvelope(), loading: true, error: null }
const listeners = new Set()
let started = false

function setState(next) {
  state = next
  for (const cb of listeners) cb()
}

/** Fetch the live envelope; fall back to bundled builtins if the endpoint is unavailable. */
export async function refreshContributions() {
  setState({ ...state, loading: true })
  try {
    const env = await api.getContributions()
    setState({ envelope: normalize(env), loading: false, error: null })
  } catch (e) {
    setState({ envelope: builtinEnvelope(), loading: false, error: e.message })
  }
  return state.envelope
}

function subscribe(cb) {
  if (!started) {
    started = true
    refreshContributions()
  }
  listeners.add(cb)
  return () => listeners.delete(cb)
}

function getSnapshot() {
  return state
}

/** React hook: the current contribution state ({ envelope, loading, error }). */
export function useContributions() {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}
