import React from 'react'

// Compact fleet-health card for the dashboard side column: the healthy/warning/critical
// distribution bar (plan 08 data) plus an aggregate RAM footer. The per-metric averages
// moved into FleetSummary's KPI tiles (with trends) — this card only answers "is anything
// unhealthy?". Renders nothing until fleet health is available.
export default function FleetHealth({ fleetHealth }) {
  if (!fleetHealth) return null

  const dist = fleetHealth.health_distribution || {}
  const total = (dist.healthy || 0) + (dist.warning || 0) + (dist.critical || 0)
  const ramUsed = fleetHealth.total_ram_used_mb
  const ramTotal = fleetHealth.total_ram_total_mb

  return (
    <div className="bg-card border border-main rounded-lg overflow-hidden">
      <div className="p-4 border-b border-main bg-zinc-900/30">
        <h3 className="text-sm font-semibold">Fleet Health</h3>
      </div>
      <div className="p-4 space-y-3">
        {total > 0 ? (
          <>
            <div className="flex h-3 rounded-full overflow-hidden bg-hover">
              {dist.healthy > 0 && (
                <div
                  className="bg-emerald-500 transition-all"
                  style={{ width: `${(dist.healthy / total) * 100}%` }}
                />
              )}
              {dist.warning > 0 && (
                <div
                  className="bg-amber-500 transition-all"
                  style={{ width: `${(dist.warning / total) * 100}%` }}
                />
              )}
              {dist.critical > 0 && (
                <div
                  className="bg-red-500 transition-all"
                  style={{ width: `${(dist.critical / total) * 100}%` }}
                />
              )}
            </div>
            <div className="flex gap-4 text-[10px]">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500" /> Healthy: {dist.healthy}
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-amber-500" /> Warning: {dist.warning}
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-red-500" /> Critical: {dist.critical}
              </span>
            </div>
          </>
        ) : (
          <p className="text-xs text-zinc-600">No health data yet.</p>
        )}
        {ramTotal > 0 && (
          <div className="flex items-center justify-between pt-3 border-t border-main text-[10px]">
            <span className="font-bold text-zinc-500 uppercase tracking-widest">RAM in use</span>
            <span className="mono text-zinc-300">
              {(ramUsed / 1024).toFixed(1)} / {(ramTotal / 1024).toFixed(1)} GB
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
