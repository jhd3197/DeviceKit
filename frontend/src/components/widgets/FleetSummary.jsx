import React from 'react'
import MetricCard from '../ds/MetricCard'

// Top-line fleet stats: connected devices plus fleet-average CPU / battery / temperature,
// with 24h trend sparklines where history exists. Deliberately few tiles — the health
// distribution and run activity live in the side-column widgets. AI spend only appears
// once there is any.
export default function FleetSummary({ devices = [], fleetHealth, fleetAiCost = 0, trends = {} }) {
  const online = devices.filter((d) => d.online !== false).length
  const showCost = fleetAiCost > 0

  return (
    <div className={`grid gap-4 grid-cols-2 ${showCost ? 'xl:grid-cols-5' : 'xl:grid-cols-4'}`}>
      <MetricCard
        label="Devices"
        value={online}
        unit={`of ${devices.length} online`}
      />
      <MetricCard
        label="Avg CPU"
        value={fleetHealth ? `${fleetHealth.avg_cpu}%` : '—'}
        valueClass={fleetHealth?.avg_cpu > 80 ? 'text-red-400' : ''}
        spark={trends.cpu}
      />
      <MetricCard
        label="Avg Battery"
        value={fleetHealth ? `${fleetHealth.avg_battery}%` : '—'}
        valueClass={fleetHealth?.avg_battery < 20 ? 'text-red-400' : ''}
        spark={trends.battery}
        sparkColor={fleetHealth?.avg_battery < 20 ? '#ef4444' : '#10b981'}
      />
      <MetricCard
        label="Avg Temp"
        value={fleetHealth ? `${fleetHealth.avg_temperature}°C` : '—'}
        valueClass={fleetHealth?.avg_temperature > 45 ? 'text-red-400' : ''}
      />
      {showCost && (
        <MetricCard label="AI Spend" value={`$${fleetAiCost.toFixed(2)}`} />
      )}
    </div>
  )
}
