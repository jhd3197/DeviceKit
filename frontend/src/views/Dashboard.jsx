import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronRight, Smartphone, X } from 'lucide-react'
import { api } from '../api'
import ExtensionSlot from '../extensions/ExtensionSlot'
import useFleetData from '../hooks/useFleetData'
import FleetSummary from '../components/widgets/FleetSummary'
import FleetHealth from '../components/widgets/FleetHealth'
import FQLBar from '../components/widgets/FQLBar'
import DeviceRegistry from '../components/widgets/DeviceRegistry'

// Fleet Overview dashboard. A thin composer over self-contained widgets (plan 11): shared
// fleet data comes from useFleetData, the FQL bar reports its result set up so the registry
// can show matches, and each widget owns its own presentation. Layout is fixed here in
// phase 1; phase 2 makes it toggleable/reorderable via useDashboardLayout.
export default function Dashboard() {
  const [searchParams] = useSearchParams()
  const initialQuery = searchParams.get('q') || ''
  const {
    stats, devices, fleetHealth, fleetAiCost, sparklines, sseConnected,
    loading, error, toasts, dismissToast,
  } = useFleetData()

  // Cross-widget link: the FQL bar owns the query, the registry renders its matches.
  const [queryResult, setQueryResult] = useState({ active: false, matches: null })

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-zinc-500 text-sm mono">Loading fleet data...</span>
      </div>
    )
  }

  return (
    <>
      {/* Header */}
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-black/50 backdrop-blur-md shrink-0">
        <div className="flex items-center gap-2 text-xs font-medium text-zinc-500">
          <span>Infrastructure</span>
          <ChevronRight className="w-3 h-3" />
          <span className="text-zinc-200">Fleet Overview</span>
        </div>
        <div className="flex items-center gap-4">
          <div className={`flex items-center gap-2 text-[10px] mono px-2 py-1 rounded border ${
            sseConnected
              ? 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20'
              : 'text-red-400 bg-red-500/10 border-red-500/20'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${sseConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
            {sseConnected ? 'LIVE' : 'RECONNECTING'}
          </div>
          <button className="bg-white text-black text-xs font-bold px-4 py-1.5 rounded hover:bg-zinc-200 transition-colors">
            Deploy Update
          </button>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8 space-y-8 max-w-7xl">
        {error && (
          <div className="bg-red-950/50 border border-red-900/50 rounded-lg p-3 text-xs text-red-400">
            {error}
          </div>
        )}

        {/* Extension widgets contributed to the dashboard top (plan 04) */}
        <ExtensionSlot name="dashboard.top" className="grid gap-4 md:grid-cols-2" />

        <FleetSummary stats={stats} fleetAiCost={fleetAiCost} />
        <FleetHealth fleetHealth={fleetHealth} />
        <FQLBar initialQuery={initialQuery} onResult={setQueryResult} />
        <DeviceRegistry devices={devices} sparklines={sparklines} queryResult={queryResult} />
      </div>

      {/* Auto-onboarding toasts */}
      {toasts.length > 0 && (
        <div className="fixed bottom-6 right-6 z-50 space-y-2">
          {toasts.map((t) => (
            <div
              key={t.id}
              className="bg-blue-950 border border-blue-800/50 rounded-lg p-4 flex items-center gap-3 shadow-lg min-w-[300px] animate-[fadeIn_0.3s_ease-out]"
            >
              <Smartphone className="w-5 h-5 text-blue-400 shrink-0" />
              <div className="flex-1">
                <p className="text-xs font-semibold text-blue-200">New device detected</p>
                <p className="text-[10px] mono text-blue-400 mt-0.5">{t.device_id}</p>
              </div>
              <button
                onClick={async () => {
                  try { await api.onboardDevice(t.device_id) } catch {}
                  dismissToast(t.id)
                }}
                className="bg-blue-600 hover:bg-blue-500 text-white text-[10px] font-bold px-3 py-1 rounded transition-colors shrink-0"
              >
                Install Agent
              </button>
              <button
                onClick={() => dismissToast(t.id)}
                className="text-blue-600 hover:text-blue-400 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
