// Command Palette (plan 10, extended by plan 26) — jump-to-anything.
//
// One cmdk-backed dialog, mounted once in App.jsx. Open with `Ctrl/Cmd+K`, `Ctrl/Cmd+Shift+P`,
// or `F1`. It merges several sources, driven by our own fuzzy scorer (`shouldFilter={false}`) so
// ranking is consistent across categories and a three-letter serial fragment beats scanning a
// fleet dashboard. Final score = fuzzy + category weight + capped frecency.
//   - Pages / Actions — static lists mirroring the sidebar + common verbs.
//   - Settings        — every indexed settings card; enter deep-links + flashes the card (plan 26).
//   - Entities        — devices/automations/profiles/groups/extensions/jobs/(users/workspaces),
//                       fetched from the authz-scoped `/search` on a 200 ms debounce, ≥2 chars
//                       (plan 26 part 3) — no more fetch-every-table-on-open.
//   - Extensions      — `command_palette` contributions from installed extensions.
// Recents come from `utils/paletteFrecency.js` (14-day half-life). A `>`-prefixed query switches
// to FQL mode and runs `/fleet/query` inline (plan 10). Admin-only results are dropped for
// non-admins via `usePaletteAuthz`.
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Command } from 'cmdk'
import { useNavigate } from 'react-router-dom'
import {
  LayoutGrid, Cpu, Terminal, Users, BarChart3, LineChart, ShieldCheck, History,
  Puzzle, PlayCircle, Workflow, Briefcase, Bell, Settings, Bot, Smartphone, Search, Plus,
  Building2,
} from 'lucide-react'
import { api } from '../api'
import { useContributions } from '../extensions/contributions'
import ExtensionIcon from '../extensions/ExtensionIcon'
import { recordUse, frecencyScore, recentEntries } from '../utils/paletteFrecency'
import { SETTINGS_INDEX } from '../data/settingsIndex'
import { usePaletteAuthz } from '../hooks/usePaletteAuthz'

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
  { to: '/settings', label: 'Settings', icon: Settings, keywords: 'settings config samanlabs' },
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

// Backend `/search` row type → palette category + icon (plan 26 part 3). The async omnisearch
// replaces fetching whole tables on open, so entity rows arrive already matched + authz-scoped.
const TYPE_META = {
  device: { group: 'Devices', icon: Smartphone },
  automation: { group: 'Automations', icon: Workflow },
  profile: { group: 'Profiles', icon: Bot },
  group: { group: 'Groups', icon: Users },
  extension: { group: 'Extensions', icon: Puzzle },
  job: { group: 'Jobs', icon: Briefcase },
  user: { group: 'Users', icon: Users },
  workspace: { group: 'Workspaces', icon: Building2 },
}

// Normalize a contribution's `keywords` (array or string) into a searchable string.
function keywordString(kw) {
  if (Array.isArray(kw)) return kw.join(' ')
  return kw || ''
}

export default function CommandPalette() {
  const navigate = useNavigate()
  const { envelope } = useContributions()
  const { allow } = usePaletteAuthz()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searchLoading, setSearchLoading] = useState(false)
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

  // Reset query on close; refresh the frecency-ranked recents on open. Entities are no longer
  // pre-fetched here (plan 26 part 3) — they come from the debounced `/search` effect below.
  useEffect(() => {
    if (!open) {
      setQuery('')
      setSearchResults([])
      return
    }
    setRecents(recentEntries(RECENTS_MAX))
  }, [open])

  // Debounced entity omnisearch (plan 26 part 3). Outside FQL mode, a ≥2-char query hits the
  // authz-scoped `/search` once per 200 ms instead of pre-loading every table. Results arrive
  // pre-matched + workspace/role-scoped; the client only ranks + buckets them.
  useEffect(() => {
    if (!open || fqlMode) { setSearchResults([]); setSearchLoading(false); return }
    const q = query.trim()
    if (q.length < 2) { setSearchResults([]); setSearchLoading(false); return }
    setSearchLoading(true)
    let cancelled = false
    const t = setTimeout(() => {
      api.search(q)
        .then((r) => { if (!cancelled) { setSearchResults(r.results || []); setSearchLoading(false) } })
        .catch(() => { if (!cancelled) { setSearchResults([]); setSearchLoading(false) } })
    }, 200)
    return () => { cancelled = true; clearTimeout(t) }
  }, [open, fqlMode, query])

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

  // Build the flat item list of *static* sources (pages, actions, settings, extensions). Live
  // entities (devices/automations/profiles/…) now come from the async `/search` provider below.
  // Items with a `path` navigate on select and are eligible for recents; a custom `onRun` overrides.
  const items = useMemo(() => {
    const out = []
    for (const p of PAGES) {
      out.push({ id: `page:${p.to}`, group: 'Pages', label: p.label, keywords: p.keywords, icon: p.icon, path: p.to })
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
    // Settings omnisearch (plan 26): every indexed settings card. Selecting one deep-links to
    // `/settings/<tab>?focus=setting:<id>`, where useSettingFocus scrolls it in + flashes it.
    for (const s of SETTINGS_INDEX) {
      out.push({
        id: `setting:${s.id}`,
        group: 'Settings',
        label: s.label,
        sublabel: s.tab,
        keywords: `${s.label} ${s.description || ''} ${s.keywords || ''} ${s.tab} settings`,
        icon: Settings,
        adminOnly: s.adminOnly,
        path: `/settings/${s.tab}?focus=setting:${s.id}`,
      })
    }
    // Authz: never surface something the user can't reach (admin-only cards for non-admins).
    return out.filter(allow)
  }, [extEntries, allow])

  // Live entity rows from the backend `/search` provider, mapped to palette categories. These are
  // already matched + authz-scoped server-side, so they bypass the client fuzzy filter (floored
  // at score 0) — a serial fragment always shows even if the label doesn't fuzzy-match.
  const entityItems = useMemo(() => {
    return searchResults.map((r, i) => {
      const meta = TYPE_META[r.type] || { group: 'Results', icon: Search }
      return {
        id: `search:${r.type}:${r.path}:${i}`,
        group: meta.group,
        label: r.label,
        sublabel: r.sublabel,
        keywords: `${r.label} ${r.sublabel || ''}`,
        icon: meta.icon,
        path: r.path,
        entity: true,
      }
    }).filter(allow)
  }, [searchResults, allow])

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
      // Empty state browses recents + destinations, but not the ~dozens of settings cards —
      // those surface only once the user types (they'd flood the empty listing otherwise).
      list = [...recentItems, ...items.filter((it) => it.group !== 'Settings')]
    } else {
      // Final score = fuzzy + category weight + capped frecency (plan 26). Static items are
      // client fuzzy-filtered; entity rows from `/search` are pre-matched server-side so their
      // fuzzy score is floored at 0 (a serial fragment always shows even without a label match).
      const staticScored = items
        .map((it) => {
          const fuzzy = scoreItem(it, q)
          if (fuzzy < 0) return null
          return { it, score: fuzzy + groupWeight(it.group) + Math.min(frecencyScore(it.id), 10) }
        })
        .filter(Boolean)
      const entityScored = entityItems.map((it) => {
        const fuzzy = Math.max(scoreItem(it, q), 0)
        return { it, score: fuzzy + groupWeight(it.group) + Math.min(frecencyScore(it.id), 10) }
      })
      list = [...staticScored, ...entityScored]
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
  }, [items, entityItems, recentItems, query])

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
                {searchLoading ? 'Searching…' : 'No results found.'}
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
