import React from 'react'
import MetricCard from '../ds/MetricCard'

// Top-line fleet counters: node count, utilization, response, health, and aggregate AI
// cost. Self-contained widget carved from Dashboard.jsx (plan 11); reads shared fleet data
// via props from the dashboard composer.
export default function FleetSummary({ stats, fleetAiCost = 0 }) {
  return (
    <div className="grid grid-cols-5 gap-4">
      <MetricCard label="Global Fleet" value={stats?.fleet_count ?? 0} unit="Nodes" />
      <MetricCard
        label="Active Utilization"
        value={`${stats?.utilization ?? 0}%`}
        valueClass="text-emerald-500"
      />
      <MetricCard label="Avg Response" value={`${stats?.avg_response_ms ?? 0}ms`} />
      <MetricCard
        label="System Health"
        value={stats?.health ?? 'Unknown'}
        valueClass={stats?.health === 'Healthy' ? 'text-emerald-400' : 'text-red-400'}
      />
      <MetricCard
        label="Fleet AI Cost"
        value={`$${fleetAiCost.toFixed(2)}`}
        valueClass={fleetAiCost > 0 ? 'text-blue-400' : 'text-zinc-400'}
      />
    </div>
  )
}
