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
  Puzzle, PlayCircle, Workflow, Briefcase, Bell, Settings, Bot, Smartphone, Search,
} from 'lucide-react'
import { api } from '../api'

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

// Group render order.
const GROUP_ORDER = ['Pages', 'Devices', 'Automations']

export default function CommandPalette() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [devices, setDevices] = useState([])
  const [automations, setAutomations] = useState([])

  // Global Ctrl/Cmd+K toggles the palette; Escape closes it. The chord fires regardless of
  // focus so it works from inside any input.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
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
    let cancelled = false
    api.getDevices().then((r) => { if (!cancelled) setDevices(r.devices || []) }).catch(() => {})
    api.getAutomations().then((r) => { if (!cancelled) setAutomations(r.automations || []) }).catch(() => {})
    return () => { cancelled = true }
  }, [open])

  const close = useCallback(() => setOpen(false), [])

  const run = useCallback((fn) => {
    close()
    fn()
  }, [close])

  // Build the flat item list from every source. Each item carries its own `run` action.
  const items = useMemo(() => {
    const out = []
    for (const p of PAGES) {
      out.push({
        id: `page:${p.to}`,
        group: 'Pages',
        label: p.label,
        keywords: p.keywords,
        icon: p.icon,
        onRun: () => navigate(p.to),
      })
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
        onRun: () => navigate(`/node/${id}`),
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
        onRun: () => navigate(`/automations/${a.id}/edit`),
      })
    }
    return out
  }, [devices, automations, navigate])

  // Filter + rank against the query, then bucket by group in fixed order.
  const grouped = useMemo(() => {
    const q = query.trim()
    let list
    if (!q) {
      list = items
    } else {
      list = items
        .map((it) => ({ it, score: scoreItem(it, q) }))
        .filter((x) => x.score >= 0)
        .sort((a, b) => b.score - a.score)
        .map((x) => x.it)
    }
    const byGroup = new Map()
    for (const it of list) {
      if (!byGroup.has(it.group)) byGroup.set(it.group, [])
      byGroup.get(it.group).push(it)
    }
    return GROUP_ORDER
      .filter((g) => byGroup.has(g))
      .map((g) => ({ group: g, items: byGroup.get(g) }))
  }, [items, query])

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
            <Search className="w-4 h-4 text-zinc-500 shrink-0" />
            <Command.Input
              value={query}
              onValueChange={setQuery}
              placeholder="Search pages, devices, automations…"
              autoFocus
              className="flex-1 bg-transparent py-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none"
            />
            <kbd className="text-[10px] text-zinc-600 border border-main rounded px-1.5 py-0.5 mono">ESC</kbd>
          </div>

          <Command.List className="max-h-[52vh] overflow-y-auto p-2">
            <Command.Empty className="px-3 py-8 text-center text-xs text-zinc-500">
              No results found.
            </Command.Empty>

            {grouped.map(({ group, items: groupItems }) => (
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
                      onSelect={() => run(it.onRun)}
                      className="flex items-center gap-3 px-2 py-2 rounded-md text-sm text-zinc-300 cursor-pointer aria-selected:bg-zinc-800 aria-selected:text-white"
                    >
                      {Icon ? <Icon className="w-4 h-4 shrink-0 text-zinc-400" /> : null}
                      <span className="flex-1 min-w-0 truncate">{it.label}</span>
                      {it.group === 'Devices' && (
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
        </Command>
      </div>
    </div>
  )
}
