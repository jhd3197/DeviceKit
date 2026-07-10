// Settings shell (plan 12).
//
// A left tab nav + a single active pane, with the selected tab living in the URL
// (`/settings/:tab`) so every pane is linkable and browser-navigable. Loads the durable
// settings object once (`GET /settings`) and hands each pane `settings` + a `save(patch)`
// that PUTs just the changed keys and merges the fresh object back. Tabs are declared in
// one registry so adding a pane is a single entry; they group into labelled sections.
import React, { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Settings as SettingsIcon, KeyRound, Info, Loader2 } from 'lucide-react'

import { api } from '../api'
import General from '../components/settings/General'
import ApiAccess from '../components/settings/ApiAccess'
import About from '../components/settings/About'

// Tab registry. `section` groups items in the nav; `component` receives { settings, save }.
const TABS = [
  { id: 'general', label: 'General', icon: SettingsIcon, section: 'Workspace', component: General },
  { id: 'api', label: 'API Access', icon: KeyRound, section: 'Workspace', component: ApiAccess },
  { id: 'about', label: 'About', icon: Info, section: 'Workspace', component: About },
]

const SECTION_ORDER = ['Workspace', 'Devices & AI', 'Personalization']

function groupTabs(tabs) {
  const bySection = new Map()
  for (const t of tabs) {
    if (!bySection.has(t.section)) bySection.set(t.section, [])
    bySection.get(t.section).push(t)
  }
  return [...bySection.entries()].sort(
    (a, b) => SECTION_ORDER.indexOf(a[0]) - SECTION_ORDER.indexOf(b[0])
  )
}

export default function Settings() {
  const { tab } = useParams()
  const navigate = useNavigate()
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const activeId = TABS.some((t) => t.id === tab) ? tab : TABS[0].id
  const active = TABS.find((t) => t.id === activeId)

  useEffect(() => {
    let alive = true
    api
      .getSettings()
      .then((r) => alive && setSettings(r.settings || {}))
      .catch((e) => alive && setError(e.message || 'Failed to load settings'))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  // Persist just the changed keys and merge the server's fresh object back in.
  const save = useCallback(async (patch) => {
    const r = await api.updateSettings(patch)
    setSettings(r.settings || {})
    return r.settings
  }, [])

  // Normalize a bare /settings or an unknown tab to the canonical first tab.
  useEffect(() => {
    if (!loading && tab !== activeId) navigate(`/settings/${activeId}`, { replace: true })
  }, [loading, tab, activeId, navigate])

  const grouped = groupTabs(TABS)
  const Pane = active.component

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      {/* Header */}
      <div className="border-b border-main px-8 py-6">
        <h1 className="text-xl font-bold tracking-tight">Settings</h1>
        <p className="text-xs text-zinc-500 mt-1">Configure this DeviceKit instance.</p>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Left tab nav */}
        <nav className="w-56 border-r border-main p-4 overflow-y-auto shrink-0">
          {grouped.map(([section, items]) => (
            <div key={section} className="mb-6">
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest px-3 mb-2">
                {section}
              </p>
              {items.map((t) => (
                <button
                  key={t.id}
                  onClick={() => navigate(`/settings/${t.id}`)}
                  className={`w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                    t.id === activeId
                      ? 'bg-zinc-900 text-white'
                      : 'text-zinc-400 hover:text-white hover:bg-zinc-900'
                  }`}
                >
                  <t.icon className="w-4 h-4" />
                  {t.label}
                </button>
              ))}
            </div>
          ))}
        </nav>

        {/* Active pane */}
        <div className="flex-1 overflow-y-auto p-8">
          {loading ? (
            <p className="text-zinc-500 text-sm flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading settings…
            </p>
          ) : error ? (
            <p className="text-red-400 text-sm">{error}</p>
          ) : (
            <Pane settings={settings} save={save} />
          )}
        </div>
      </div>
    </div>
  )
}
