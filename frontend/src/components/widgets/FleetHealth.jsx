import React from 'react'
import MetricCard from '../ds/MetricCard'

// Fleet health at a glance: avg CPU/battery/RAM/temp cards plus the healthy/warning/critical
// distribution bar (plan 08 data). Renders nothing until fleet health is available. Carved
// out of Dashboard.jsx as a self-contained widget (plan 11).
export default function FleetHealth({ fleetHealth }) {
  if (!fleetHealth) return null

  const dist = fleetHealth.health_distribution || {}
  const total = (dist.healthy || 0) + (dist.warning || 0) + (dist.critical || 0)

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          label="Avg CPU"
          value={`${fleetHealth.avg_cpu}%`}
          valueClass={fleetHealth.avg_cpu > 80 ? 'text-red-400' : 'text-emerald-400'}
        />
        <MetricCard
          label="Avg Battery"
          value={`${fleetHealth.avg_battery}%`}
          valueClass={fleetHealth.avg_battery < 20 ? 'text-red-400' : 'text-white'}
        />
        <MetricCard
          label="Total RAM"
          value={`${(fleetHealth.total_ram_used_mb / 1024).toFixed(1)}`}
          unit={`/ ${(fleetHealth.total_ram_total_mb / 1024).toFixed(1)} GB`}
        />
        <MetricCard
          label="Avg Temp"
          value={`${fleetHealth.avg_temperature}°C`}
          valueClass={fleetHealth.avg_temperature > 45 ? 'text-red-400' : 'text-zinc-200'}
        />
      </div>

      {/* Health Distribution */}
      {total > 0 && (
        <div className="bg-card border border-main p-4 rounded-lg">
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">
            Fleet Health Distribution
          </p>
          <div className="flex h-3 rounded-full overflow-hidden bg-zinc-900">
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
          <div className="flex gap-4 mt-2 text-[10px]">
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
        </div>
      )}
    </div>
  )
}
