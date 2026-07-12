// Command Palette (plan 10) — `Ctrl/Cmd+K` jump-to-anything.
//
// One cmdk-backed dialog, mounted once in App.jsx, that merges several sources at open time:
//   - Pages     — a static list mirroring App.jsx `navSections`.
//   - Devices   — fetched from `/devices` on open; enter → `/node/<id>`.
//   - Automations — fetched from `/automations` on open; enter → editor.
// Sources are fetched only while the palette is open (not kept hot). We drive cmdk with our
// own fuzzy scorer (`shouldFilter={false}`) so ranking is consistent across categories and a
// three-letter serial fragment beats dashboard-scanning a 30-device fleet.
//
// Phase 2 adds Actions, localStorage recents, and extension `command_palette` contributions;
// phase 3 adds FQL mode (a `>`-prefixed query runs `/fleet/query` inline).
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Command } from 'cmdk'
import { useNavigate } from 'react-router-dom'
import {
  LayoutGrid, Cpu, Terminal, Users, BarChart3, LineChart, ShieldCheck, History,
  Puzzle, PlayCircle, Workflow, Briefcase, Bell, Settings, Bot, Smartphone, Search, Plus,
} from 'lucide-react'
import { api } from '../api'
import { useContributions } from '../extensions/contributions'
import ExtensionIcon from '../extensions/ExtensionIcon'
import { recordUse, frecencyScore, recentEntries } from '../utils/paletteFrecency'

// Static pages — mirrors the sidebar `navSections` in App.jsx. Keep in sync when nav changes.
const PAGES = [
  { to: '/', label: 'Fleet Overview', icon: LayoutGrid, keywords: 'dashboard home devices overview' },
  { to: '/node', label: 'Node Control', icon: Cpu, keywords: 'device detail control' },
  { to: '/remote-adb', label: 'Remote ADB', icon: Terminal, keywords: 'shell console terminal adb' },
  { to: '/fleet/groups', label: 'Device Groups', icon: Users, keywords: 'fleet groups tags' },
  { to: '/fleet/compare', label: 'Compare', icon: BarChart3, keywords: 'compare devices diff' },
  { to: '/fleet/monitor', label: 'Metrics Monitor', icon: LineChart, keywords: 'metrics charts history monitor' },
  { to: '/enrollment', label: 'Enrollment', icon: ShieldCheck, keywords: 'enroll claim pairing agent' },
  { to: '/command-history', label: 'Command History', icon: History, keywords: 'commands history audit' },
  { to: '/extensions', label: 'Extensions', icon: Puzzle, keywords: 'plugins marketplace install' },
  { to: '/pipeline', label: 'Pipeline', icon: PlayCircle, keywords: 'builds ci tests pipeline' },
  { to: '/automations', label: 'Automations', icon: Workflow, keywords: 'automation flows steps' },
  { to: '/jobs', label: 'Jobs', icon: Briefcase, keywords: 'jobs scheduler queue' },
  { to: '/notifications', label: 'Notifications', icon: Bell, keywords: 'alerts notifications channels' },
  { to: '/settings', label: 'SamanLabs Config', icon: Settings, keywords: 'settings config' },
  { to: '/profiles', label: 'Profiles', icon: Bot, keywords: 'ai profiles agent model' },
]

// Static actions — verbs, not destinations. Extension `command_palette` entries merge in as
// their own groups (default "Extensions").
const ACTIONS = [
  { id: 'action:new-automation', label: 'New Automation', path: '/automations/new', icon: Plus, keywords: 'create new automation flow' },
  { id: 'action:compare', label: 'Compare Devices', path: '/fleet/compare', icon: BarChart3, keywords: 'compare diff devices' },
  { id: 'action:new-profile', label: 'New Profile', path: '/profiles/new', icon: Bot, keywords: 'create new profile ai model' },
  { id: 'action:install-extension', label: 'Install Extension', path: '/extensions', icon: Puzzle, keywords: 'install extension plugin marketplace' },
]

// Recents are sourced from `utils/paletteFrecency.js` (plan 26) — a frequency+recency blend with
// a 14-day half-life — replacing the old last-6 list. On an empty query the top frecency entries
// show as the "Recents" group; on a live query each item's frecency is blended into its score.
const RECENTS_MAX = 8

// --- Fuzzy scorer (ported from ServerKit's small scorer) ----------------------------------
// substring match (prefix > word-boundary > mid-string) scores highest; a subsequence match is
// the fallback. Returns -1 for no match. Higher is better.
function fuzzyScore(text, query) {
  if (!query) return 0
  text = text.toLowerCase()
  query = query.toLowerCase()
  if (text === query) return 1000
  const idx = text.indexOf(query)
  if (idx === 0) return 900 - text.length * 0.1
  if (idx > 0) {
    const boundary = /[\s\-_/.]/.test(text[idx - 1])
    return (boundary ? 700 : 500) - idx - text.length * 0.1
  }
  // Subsequence: every query char appears in order; consecutive hits score more.
  let qi = 0
  let score = 0
  let last = -2
  for (let i = 0; i < text.length && qi < query.length; i++) {
    if (text[i] === query[qi]) {
      score += i === last + 1 ? 6 : 1
      last = i
      qi++
    }
  }
  return qi === query.length ? 100 + score - text.length * 0.05 : -1
}

// Score an item against a query across its label + keyword fields; best field wins.
function scoreItem(item, query) {
  const fields = [item.label, item.sublabel, item.keywords]
  let best = -1
  for (const f of fields) {
    if (!f) continue
    const s = fuzzyScore(String(f), query)
    if (s > best) best = s
  }
  return best
}

// Group render order. Known groups get a fixed rank; extension-contributed categories sort
// after Actions (rank 5) and before the catch-all "Extensions" group.
const GROUP_RANK = { Recents: 0, Pages: 1, Devices: 2, Automations: 3, Actions: 4 }
function groupRank(g) {
  if (g in GROUP_RANK) return GROUP_RANK[g]
  return g === 'Extensions' ? 6 : 5
}

// Category weights (plan 26) — a small tie-breaker blended into the live score so that, among
// equally-good fuzzy matches, higher-signal groups win. Settings deep-links (phase 2) and
// pages/actions rank above raw entity rows; frecency (capped) adds the "you use this a lot" nudge.
const GROUP_WEIGHT = { Settings: 6, Pages: 4, Actions: 4, Devices: 1, Automations: 1 }
function groupWeight(g) {
  return GROUP_WEIGHT[g] ?? 1
}

// Normalize a contribution's `keywords` (array or string) into a searchable string.
function keywordString(kw) {
  if (Array.isArray(kw)) return kw.join(' ')
  return kw || ''
}

export default function CommandPalette() {
  const navigate = useNavigate()
  const { envelope } = useContributions()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [devices, setDevices] = useState([])
  const [automations, setAutomations] = useState([])
  const [recents, setRecents] = useState(() => recentEntries(RECENTS_MAX))
  const [fql, setFql] = useState({ matches: [], total: 0, loading: false, error: null })

  // FQL mode: a `>`-prefixed query runs `/fleet/query` inline. `fqlExpr` is the expression
  // after the `>` (empty string until the user types one); null means we're not in FQL mode.
  const fqlExpr = useMemo(() => {
    const t = query.trimStart()
    return t.startsWith('>') ? t.slice(1).trim() : null
  }, [query])
  const fqlMode = fqlExpr !== null

  // Global open bindings (plan 26): `Ctrl/Cmd+K`, `Ctrl/Cmd+Shift+P` (VS Code muscle memory),
  // and `F1`. Escape closes. All fire regardless of focus so they work from inside any input;
  // `F1` needs an explicit `preventDefault` to stop the browser help panel.
  useEffect(() => {
    const onKey = (e) => {
      const cmdK = (e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')
      const cmdShiftP = (e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === 'p' || e.key === 'P')
      const f1 = e.key === 'F1'
      if (cmdK || cmdShiftP || f1) {
        e.preventDefault()
        setOpen((v) => !v)
      } else if (e.key === 'Escape' && open) {
        setOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  // Fetch live sources each time the palette opens (not kept hot); reset query on close.
  useEffect(() => {
    if (!open) {
      setQuery('')
      return
    }
    // Refresh the frecency-ranked recents each open so they reflect uses since last time.
    setRecents(recentEntries(RECENTS_MAX))
    let cancelled = false
    api.getDevices().then((r) => { if (!cancelled) setDevices(r.devices || []) }).catch(() => {})
    api.getAutomations().then((r) => { if (!cancelled) setAutomations(r.automations || []) }).catch(() => {})
    return () => { cancelled = true }
  }, [open])

  // Debounced FQL execution — reuses the untouched `/fleet/query` endpoint. Runs only while the
  // palette is open and the query is a non-empty `>` expression.
  useEffect(() => {
    if (!open || fqlExpr === null) return
    if (!fqlExpr) {
      setFql({ matches: [], total: 0, loading: false, error: null })
      return
    }
    setFql((f) => ({ ...f, loading: true, error: null }))
    let cancelled = false
    const t = setTimeout(() => {
      api.fleetQuery(fqlExpr)
        .then((r) => { if (!cancelled) setFql({ matches: r.matches || [], total: r.total || 0, loading: false, error: null }) })
        .catch((e) => { if (!cancelled) setFql({ matches: [], total: 0, loading: false, error: e.message || 'Query failed' }) })
    }, 250)
    return () => { cancelled = true; clearTimeout(t) }
  }, [open, fqlExpr])

  const close = useCallback(() => setOpen(false), [])

  // Execute an item: close, run its action (custom `onRun` or navigate to `path`), and record
  // the use in frecency when it has a stable `path` (meta lets recents render even for items not
  // in the current live list, e.g. an offline device).
  const runItem = useCallback((item) => {
    if (!item.keepOpen) close()
    if (item.onRun) item.onRun()
    else if (item.path) navigate(item.path)
    if (item.path) {
      recordUse(item.id, {
        label: item.label,
        sublabel: item.sublabel,
        group: item.group,
        path: item.path,
      })
      setRecents(recentEntries(RECENTS_MAX))
    }
  }, [close, navigate])

  const extEntries = envelope.command_palette || []

  // Build the flat item list from every source. Items with a `path` navigate on select and are
  // eligible for recents; a custom `onRun` overrides.
  const items = useMemo(() => {
    const out = []
    for (const p of PAGES) {
      out.push({ id: `page:${p.to}`, group: 'Pages', label: p.label, keywords: p.keywords, icon: p.icon, path: p.to })
    }
    for (const d of devices) {
      const id = d.device_id || d.serial
      if (!id) continue
      out.push({
        id: `device:${id}`,
        group: 'Devices',
        label: d.model || d.name || id,
        sublabel: id,
        keywords: `${id} ${d.model || ''} ${d.manufacturer || ''}`,
        icon: Smartphone,
        online: d.online,
        path: `/node/${id}`,
      })
    }
    for (const a of automations) {
      if (!a.id) continue
      out.push({
        id: `automation:${a.id}`,
        group: 'Automations',
        label: a.name || 'Untitled automation',
        sublabel: a.description || `${(a.steps || []).length} steps`,
        keywords: `${a.name || ''} ${a.description || ''}`,
        icon: Workflow,
        path: `/automations/${a.id}/edit`,
      })
    }
    for (const ac of ACTIONS) {
      out.push({ id: ac.id, group: 'Actions', label: ac.label, keywords: ac.keywords, icon: ac.icon, path: ac.path })
    }
    // Discoverability entry for FQL mode: seeds the input with `> ` and keeps the palette open.
    out.push({
      id: 'action:fleet-query',
      group: 'Actions',
      label: 'Query Fleet…',
      sublabel: '> battery < 20',
      keywords: 'fql query fleet filter search devices expression',
      icon: Search,
      keepOpen: true,
      onRun: () => setQuery('> '),
    })
    for (const e of extEntries) {
      if (!e.path) continue
      out.push({
        id: `ext:${e.slug || ''}:${e.path}`,
        group: e.category || 'Extensions',
        label: e.label || e.path,
        keywords: `${e.label || ''} ${keywordString(e.keywords)}`,
        extIcon: e.icon,
        icon: e.icon ? null : Puzzle,
        path: e.path,
      })
    }
    return out
  }, [devices, automations, extEntries])

  // Recent items (shown only on an empty query). Re-resolve each recent's live icon/action from
  // the current item list when possible; fall back to plain path navigation for stale entries.
  const recentItems = useMemo(() => {
    const byId = new Map(items.map((it) => [it.id, it]))
    return recents.map((r) => {
      const live = byId.get(r.id)
      return {
        id: `recent:${r.id}`,
        group: 'Recents',
        label: r.label,
        sublabel: r.sublabel,
        icon: live?.icon || History,
        extIcon: live?.extIcon,
        path: r.path,
      }
    })
  }, [recents, items])

  // FQL results as palette items: an "Open in Dashboard" action first, then a device row per
  // match. Only computed while in FQL mode with a non-empty expression.
  const fqlItems = useMemo(() => {
    if (!fqlMode || !fqlExpr) return []
    const out = [{
      id: 'fql:open-dashboard',
      group: 'Fleet Query',
      label: 'Open in Dashboard',
      sublabel: fql.matches.length ? `${fql.matches.length} of ${fql.total}` : undefined,
      icon: LayoutGrid,
      path: `/?q=${encodeURIComponent(fqlExpr)}`,
    }]
    for (const d of fql.matches) {
      const id = d.device_id || d.serial
      if (!id) continue
      out.push({
        id: `fql-device:${id}`,
        group: 'Fleet Query',
        label: d.model || d.name || id,
        sublabel: id,
        icon: Smartphone,
        online: d.online,
        path: `/node/${id}`,
      })
    }
    return out
  }, [fqlMode, fqlExpr, fql.matches, fql.total])

  // Filter + rank against the query, then bucket by group in rank order. Recents replace the
  // full listing while the query is empty.
  const grouped = useMemo(() => {
    const q = query.trim()
    let list
    if (!q) {
      list = [...recentItems, ...items]
    } else {
      // Final score = fuzzy + category weight + capped frecency (plan 26): among comparable
      // fuzzy matches, higher-signal groups and items you use often float up.
      list = items
        .map((it) => {
          const fuzzy = scoreItem(it, q)
          if (fuzzy < 0) return null
          return { it, score: fuzzy + groupWeight(it.group) + Math.min(frecencyScore(it.id), 10) }
        })
        .filter(Boolean)
        .sort((a, b) => b.score - a.score)
        .map((x) => x.it)
    }
    const byGroup = new Map()
    for (const it of list) {
      if (!byGroup.has(it.group)) byGroup.set(it.group, [])
      byGroup.get(it.group).push(it)
    }
    return [...byGroup.keys()]
      .sort((a, b) => groupRank(a) - groupRank(b) || a.localeCompare(b))
      .map((g) => ({ group: g, items: byGroup.get(g) }))
  }, [items, recentItems, query])

  // In FQL mode the fleet-query results replace the normal listing.
  const displayGroups = fqlMode
    ? (fqlItems.length ? [{ group: 'Fleet Query', items: fqlItems }] : [])
    : grouped

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[12vh] px-4"
      onMouseDown={close}
    >
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-xl bg-zinc-900 border border-main rounded-xl shadow-2xl overflow-hidden"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <Command shouldFilter={false} label="Command Palette" className="flex flex-col">
          <div className="flex items-center gap-2 px-4 border-b border-main">
            {fqlMode ? (
              <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 shrink-0">FQL</span>
            ) : (
              <Search className="w-4 h-4 text-zinc-500 shrink-0" />
            )}
            <Command.Input
              value={query}
              onValueChange={setQuery}
              placeholder="Search… or > for a fleet query (e.g. > battery < 20)"
              autoFocus
              className="flex-1 bg-transparent py-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none"
            />
            <kbd className="text-[10px] text-zinc-600 border border-main rounded px-1.5 py-0.5 mono">ESC</kbd>
          </div>

          <Command.List className="max-h-[52vh] overflow-y-auto p-2">
            {fqlMode ? (
              (!fqlExpr || fql.loading || fql.error || fqlItems.length === 0) && (
                <div className="px-3 py-8 text-center text-xs">
                  {!fqlExpr ? (
                    <span className="text-zinc-500">Type a fleet query, e.g. <span className="mono text-zinc-400">battery &lt; 20 and online</span></span>
                  ) : fql.loading ? (
                    <span className="text-zinc-500">Running query…</span>
                  ) : fql.error ? (
                    <span className="text-red-400">{fql.error}</span>
                  ) : (
                    <span className="text-zinc-500">No devices match <span className="mono text-zinc-400">{fqlExpr}</span></span>
                  )}
                </div>
              )
            ) : (
              <Command.Empty className="px-3 py-8 text-center text-xs text-zinc-500">
                No results found.
              </Command.Empty>
            )}

            {displayGroups.map(({ group, items: groupItems }) => (
              <Command.Group
                key={group}
                heading={group}
                className="mb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-bold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-zinc-500"
              >
                {groupItems.map((it) => {
                  const Icon = it.icon
                  return (
                    <Command.Item
                      key={it.id}
                      value={it.id}
                      onSelect={() => runItem(it)}
                      className="flex items-center gap-3 px-2 py-2 rounded-md text-sm text-zinc-300 cursor-pointer aria-selected:bg-zinc-800 aria-selected:text-white"
                    >
                      {Icon ? (
                        <Icon className="w-4 h-4 shrink-0 text-zinc-400" />
                      ) : it.extIcon ? (
                        <ExtensionIcon svg={it.extIcon} className="w-4 h-4 shrink-0 text-zinc-400" />
                      ) : null}
                      <span className="flex-1 min-w-0 truncate">{it.label}</span>
                      {it.online !== undefined && (
                        <span
                          className={`w-1.5 h-1.5 rounded-full shrink-0 ${it.online ? 'bg-emerald-500' : 'bg-zinc-600'}`}
                        />
                      )}
                      {it.sublabel && (
                        <span className="text-[11px] text-zinc-600 mono truncate max-w-[45%]">{it.sublabel}</span>
                      )}
                    </Command.Item>
                  )
                })}
              </Command.Group>
            ))}
          </Command.List>

          {/* Footer hint row (plan 26). `?` docs mode is deferred until an in-app docs route
              exists (plan 16) — advertised only when routable. */}
          <div className="flex items-center gap-3 px-4 py-2 border-t border-main text-[10px] text-zinc-600">
            <span><kbd className="mono text-zinc-500">↵</kbd> open</span>
            <span><kbd className="mono text-zinc-500">&gt;</kbd> query fleet</span>
            <span><kbd className="mono text-zinc-500">esc</kbd> close</span>
            <span className="ml-auto text-zinc-700 mono">F1 · ⌘K · ⌘⇧P</span>
          </div>
        </Command>
      </div>
    </div>
  )
}
