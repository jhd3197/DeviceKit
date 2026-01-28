import React from 'react'
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
} from 'lucide-react'

import Dashboard from './views/Dashboard'
import NodeDetail from './views/NodeDetail'
import Pipeline from './views/Pipeline'
import RemoteADB from './views/RemoteADB'
import Automations from './views/Automations'
import AutomationEditor from './views/AutomationEditor'
import AutomationRunDetail from './views/AutomationRunDetail'

const navSections = [
  {
    label: 'Management',
    items: [
      { to: '/', icon: LayoutGrid, label: 'Fleet Overview' },
      { to: '/node', icon: Cpu, label: 'Node Control' },
      { to: '/remote-adb', icon: Terminal, label: 'Remote ADB' },
    ],
  },
  {
    label: 'Engineering',
    items: [
      { to: '/pipeline', icon: PlayCircle, label: 'Pipeline' },
      { to: '/automations', icon: Workflow, label: 'Automations' },
      { to: '/settings', icon: Settings, label: 'SamanLabs Config' },
    ],
  },
]

function Sidebar() {
  return (
    <aside className="w-64 border-r border-main flex flex-col bg-black shrink-0">
      {/* Logo */}
      <div className="p-6 flex items-center gap-3 border-b border-main">
        <div className="w-8 h-8 bg-white rounded flex items-center justify-center">
          <Layers className="text-black w-5 h-5" />
        </div>
        <span className="font-bold tracking-tight text-lg">DeviceKit</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        {navSections.map((section) => (
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
                <item.icon className="w-4 h-4" />
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* User card */}
      <div className="p-4 border-t border-main">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-zinc-800 border border-main flex items-center justify-center text-xs font-bold text-zinc-400">
            JD
          </div>
          <div className="flex-1 overflow-hidden">
            <p className="text-xs font-semibold truncate">Juan Denis</p>
            <p className="text-[10px] text-zinc-500 mono uppercase">
              Fort Lauderdale Node
            </p>
          </div>
        </div>
      </div>
    </aside>
  )
}

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/node/:id" element={<NodeDetail />} />
          <Route path="/node" element={<NodeDetail />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/automations" element={<Automations />} />
          <Route path="/automations/new" element={<AutomationEditor />} />
          <Route path="/automations/:id/edit" element={<AutomationEditor />} />
          <Route path="/automations/runs/:runId" element={<AutomationRunDetail />} />
          <Route path="/remote-adb" element={<RemoteADB />} />
        </Routes>
      </main>
    </div>
  )
}
