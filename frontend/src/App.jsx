import React, { useEffect } from 'react'
import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  Layers,
  LayoutGrid,
  Cpu,
  Terminal,
  Activity,
  Settings,
  PlayCircle,
  Workflow,
  Bot,
  Users,
  BarChart3,
  LineChart,
  GitBranch,
  Rocket,
  ClipboardList,
  Puzzle,
  Briefcase,
  Bell,
  ShieldCheck,
  History,
} from 'lucide-react'

import Dashboard from './views/Dashboard'
import NodeDetail from './views/NodeDetail'
import Pipeline from './views/Pipeline'
import RemoteADB from './views/RemoteADB'
import Automations from './views/Automations'
import AutomationEditor from './views/AutomationEditor'
import AutomationRunDetail from './views/AutomationRunDetail'
import WorkflowEditor from './views/WorkflowEditor'
import Profiles from './views/Profiles'
import ProfileEditor from './views/ProfileEditor'
import FleetGroups from './views/FleetGroups'
import DeviceCompare from './views/DeviceCompare'
import FleetMonitor from './views/FleetMonitor'
import FleetVersions from './views/FleetVersions'
import AgentUpdates from './views/AgentUpdates'
import Extensions from './views/Extensions'
import AgentPlugins from './views/AgentPlugins'
import Jobs from './views/Jobs'
import Notifications from './views/Notifications'
import Enrollment from './views/Enrollment'
import Onboarding from './views/Onboarding'
import CommandHistory from './views/CommandHistory'
import SettingsView from './views/Settings'

import NotificationBell from './components/NotificationBell'
import CommandPalette from './components/CommandPalette'
import { useContributions } from './extensions/contributions'
import { buildExtensionRoutes } from './extensions/ExtensionRoutes'
import ExtensionIcon from './extensions/ExtensionIcon'

// Core navigation. Extension-contributed nav items merge into these sections by `section`
// label (default "Extensions"); a contributed item whose route collides with a core route
// is dropped so core always wins (plan 04).
const navSections = [
  {
    label: 'Management',
    items: [
      { to: '/', icon: LayoutGrid, label: 'Fleet Overview' },
      { to: '/node', icon: Cpu, label: 'Node Control' },
      { to: '/remote-adb', icon: Terminal, label: 'Remote ADB' },
      { to: '/fleet/groups', icon: Users, label: 'Device Groups' },
      { to: '/fleet/compare', icon: BarChart3, label: 'Compare' },
      { to: '/fleet/monitor', icon: LineChart, label: 'Metrics Monitor' },
      { to: '/enrollment', icon: ShieldCheck, label: 'Enrollment' },
      { to: '/onboarding', icon: ClipboardList, label: 'Onboarding' },
      { to: '/fleet/versions', icon: GitBranch, label: 'Agent Versions' },
      { to: '/fleet/updates', icon: Rocket, label: 'Agent Updates' },
      { to: '/command-history', icon: History, label: 'Command History' },
      { to: '/extensions', icon: Puzzle, label: 'Extensions' },
      { to: '/agent-plugins', icon: Puzzle, label: 'Agent Plugins' },
    ],
  },
  {
    label: 'Engineering',
    items: [
      { to: '/pipeline', icon: PlayCircle, label: 'Pipeline' },
      { to: '/automations', icon: Workflow, label: 'Automations' },
      { to: '/jobs', icon: Briefcase, label: 'Jobs' },
      { to: '/notifications', icon: Bell, label: 'Notifications' },
      { to: '/settings', icon: Settings, label: 'Settings' },
    ],
  },
  {
    label: 'AI',
    items: [
      { to: '/profiles', icon: Bot, label: 'Profiles' },
    ],
  },
]

// Section order when merging: core sections first (in declared order), contributed-only
// sections (e.g. "Extensions") appended after.
const SECTION_ORDER = navSections.map((s) => s.label)

/** Merge core nav with the contributed nav entries from the envelope. Core wins on a route
 *  collision; contributed items are grouped into their `section` (default "Extensions"). */
function mergeNav(contribNav) {
  const coreRoutes = new Set()
  const sections = navSections.map((s) => {
    s.items.forEach((i) => coreRoutes.add(i.to))
    return { label: s.label, items: [...s.items] }
  })
  const byLabel = new Map(sections.map((s) => [s.label, s]))

  for (const item of contribNav || []) {
    const route = item.route
    if (!route || coreRoutes.has(route)) continue // core wins on collision
    const sectionLabel = item.section || 'Extensions'
    let section = byLabel.get(sectionLabel)
    if (!section) {
      section = { label: sectionLabel, items: [] }
      byLabel.set(sectionLabel, section)
      sections.push(section)
    }
    // De-dupe within a section by route.
    if (section.items.some((i) => i.to === route)) continue
    section.items.push({
      to: route,
      label: item.label || route,
      extIcon: item.icon,
      slug: item.slug,
    })
  }

  // Stable ordering: known sections in declared order, then any contributed-only sections.
  return sections
    .filter((s) => s.items.length)
    .sort((a, b) => {
      const ai = SECTION_ORDER.indexOf(a.label)
      const bi = SECTION_ORDER.indexOf(b.label)
      if (ai === -1 && bi === -1) return 0
      if (ai === -1) return 1
      if (bi === -1) return -1
      return ai - bi
    })
}

function Sidebar() {
  const { envelope } = useContributions()
  const sections = mergeNav(envelope.nav)

  return (
    <aside className="w-64 border-r border-main flex flex-col bg-black shrink-0">
      {/* Logo */}
      <div className="p-6 flex items-center gap-3 border-b border-main">
        <div className="w-8 h-8 bg-white rounded flex items-center justify-center">
          <Layers className="text-black w-5 h-5" />
        </div>
        <span className="font-bold tracking-tight text-lg">DeviceKit</span>
        <div className="ml-auto">
          <NotificationBell />
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        {sections.map((section) => (
          <div key={section.label}>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest px-3 mb-2 mt-6 first:mt-0">
              {section.label}
            </p>
            {section.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                    isActive
                      ? 'bg-zinc-900 text-white'
                      : 'text-zinc-400 hover:text-white hover:bg-zinc-900'
                  }`
                }
              >
                {item.icon ? (
                  <item.icon className="w-4 h-4" />
                ) : (
                  <ExtensionIcon svg={item.extIcon} className="w-4 h-4" />
                )}
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

    </aside>
  )
}

/** Update document.title from the contributed page_titles map (plan 04). Core pages keep
 *  the default title; extension routes can name their tab. */
function PageTitle({ titles }) {
  const location = useLocation()
  useEffect(() => {
    const title = titles?.[location.pathname]
    document.title = title ? `${title} · DeviceKit` : 'DeviceKit'
  }, [location.pathname, titles])
  return null
}

export default function App() {
  const { envelope } = useContributions()
  const extensionRoutes = buildExtensionRoutes(envelope.routes)

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <PageTitle titles={envelope.page_titles} />
      <CommandPalette />
      <main className="flex-1 flex flex-col overflow-hidden">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/node/:id" element={<NodeDetail />} />
          <Route path="/node" element={<NodeDetail />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/automations" element={<Automations />} />
          <Route path="/automations/new" element={<AutomationEditor />} />
          <Route path="/automations/:id/edit" element={<AutomationEditor />} />
          <Route path="/automations/:id/graph" element={<WorkflowEditor />} />
          <Route path="/automations/runs/:runId" element={<AutomationRunDetail />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/remote-adb" element={<RemoteADB />} />
          <Route path="/fleet/groups" element={<FleetGroups />} />
          <Route path="/fleet/compare" element={<DeviceCompare />} />
          <Route path="/fleet/monitor" element={<FleetMonitor />} />
          <Route path="/fleet/versions" element={<FleetVersions />} />
          <Route path="/fleet/updates" element={<AgentUpdates />} />
          <Route path="/enrollment" element={<Enrollment />} />
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/command-history" element={<CommandHistory />} />
          <Route path="/profiles" element={<Profiles />} />
          <Route path="/profiles/new" element={<ProfileEditor />} />
          <Route path="/profiles/:id/edit" element={<ProfileEditor />} />
          <Route path="/extensions" element={<Extensions />} />
          <Route path="/agent-plugins" element={<AgentPlugins />} />
          <Route path="/settings" element={<SettingsView />} />
          <Route path="/settings/:tab" element={<SettingsView />} />
          {extensionRoutes}
        </Routes>
      </main>
    </div>
  )
}
