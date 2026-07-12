// Settings shell (plan 12).
//
// A left tab nav + a single active pane, with the selected tab living in the URL
// (`/settings/:tab`) so every pane is linkable and browser-navigable. Loads the durable
// settings object once (`GET /settings`) and hands each pane `settings` + a `save(patch)`
// that PUTs just the changed keys and merges the fresh object back. Tabs are declared in
// one registry so adding a pane is a single entry; they group into labelled sections.
import React, { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Settings as SettingsIcon,
  KeyRound,
  Info,
  Loader2,
  Sparkles,
  MonitorPlay,
  Package,
  Bell,
  Palette,
  Puzzle,
  Users as UsersIcon,
  Lock,
  Building2,
  History,
  ShieldCheck,
} from 'lucide-react'

import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useSettingFocus } from '../hooks/useSettingFocus'
import { useContributions } from '../extensions/contributions'
import ExtensionSlot from '../extensions/ExtensionSlot'
import General from '../components/settings/General'
import ApiAccess from '../components/settings/ApiAccess'
import About from '../components/settings/About'
import AiSettings from '../components/settings/AiSettings'
import Streaming from '../components/settings/Streaming'
import Bundles from '../components/settings/Bundles'
import Appearance from '../components/settings/Appearance'
import NotificationsPane from '../components/settings/NotificationsPane'
import Users from '../components/settings/Users'
import ApiKeysPane from '../components/settings/ApiKeysPane'
import Workspaces from '../components/settings/Workspaces'
import Vault from '../components/settings/Vault'
import AuditLog from '../components/settings/AuditLog'
import Security from '../components/settings/Security'

// Pane that hosts extension-contributed settings forms (plan 04's `settings.panels` slot).
// Host settings + save are forwarded so a schema-driven form can read/write them.
function ExtensionPanels({ settings, save }) {
  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h2 className="text-lg font-bold tracking-tight">Extensions</h2>
        <p className="text-xs text-zinc-500 mt-1">Settings contributed by installed extensions.</p>
      </div>
      <ExtensionSlot name="settings.panels" settings={settings} save={save} className="space-y-6" />
    </div>
  )
}

// Tab registry. `section` groups items in the nav; `component` receives { settings, save }.
// `admin: true` tabs (plan 20) only render for an admin principal.
const TABS = [
  { id: 'general', label: 'General', icon: SettingsIcon, section: 'Workspace', component: General },
  { id: 'api', label: 'API Access', icon: KeyRound, section: 'Workspace', component: ApiAccess },
  { id: 'account', label: 'Account & 2FA', icon: ShieldCheck, section: 'Access & Security', component: Security },
  { id: 'users', label: 'Users', icon: UsersIcon, section: 'Access & Security', component: Users, admin: true },
  { id: 'apikeys', label: 'API Keys', icon: Lock, section: 'Access & Security', component: ApiKeysPane, admin: true },
  { id: 'workspaces', label: 'Workspaces', icon: Building2, section: 'Access & Security', component: Workspaces },
  { id: 'vault', label: 'Secrets Vault', icon: Lock, section: 'Access & Security', component: Vault, admin: true },
  { id: 'audit', label: 'Audit Log', icon: History, section: 'Access & Security', component: AuditLog, admin: true },
  { id: 'ai', label: 'AI', icon: Sparkles, section: 'Devices & AI', component: AiSettings },
  { id: 'streaming', label: 'Streaming', icon: MonitorPlay, section: 'Devices & AI', component: Streaming },
  { id: 'bundles', label: 'Debug Bundles', icon: Package, section: 'Devices & AI', component: Bundles },
  { id: 'notifications', label: 'Notifications', icon: Bell, section: 'Devices & AI', component: NotificationsPane },
  { id: 'appearance', label: 'Appearance', icon: Palette, section: 'Personalization', component: Appearance },
  { id: 'about', label: 'About', icon: Info, section: 'Workspace', component: About },
]

// The extension-panels tab only appears when an installed extension targets the slot.
const EXTENSION_TAB = {
  id: 'extensions',
  label: 'Extensions',
  icon: Puzzle,
  section: 'Personalization',
  component: ExtensionPanels,
}

const SECTION_ORDER = ['Workspace', 'Access & Security', 'Devices & AI', 'Personalization']

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
  const { envelope } = useContributions()
  const { isAdmin } = useAuth()
  // Palette settings deep-links (plan 26): reads ?focus=setting:<id> and hands panes a
  // register(id) they attach to their cards so the target scrolls into view and flashes.
  const { register } = useSettingFocus()
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Only surface the Extensions tab when something actually contributes to the slot.
  const hasExtensionPanels = (envelope.widgets || []).some((w) => w.slot === 'settings.panels')
  // Admin-only tabs (plan 20) are hidden from non-admin principals.
  const visibleTabs = TABS.filter((t) => !t.admin || isAdmin)
  const tabs = hasExtensionPanels ? [...visibleTabs, EXTENSION_TAB] : visibleTabs

  const activeId = tabs.some((t) => t.id === tab) ? tab : tabs[0].id
  const active = tabs.find((t) => t.id === activeId)

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

  const grouped = groupTabs(tabs)
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
            <Pane settings={settings} save={save} register={register} />
          )}
        </div>
      </div>
    </div>
  )
}
