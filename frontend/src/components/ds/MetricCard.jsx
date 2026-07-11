import React from 'react'

// Small labelled stat card used across dashboard widgets (fleet summary, fleet health).
// Extracted from Dashboard.jsx so widgets share one presentation primitive (plan 11).
export default function MetricCard({ label, value, unit, valueClass = '' }) {
  return (
    <div className="bg-card border border-main p-4 rounded-lg">
      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
        {label}
      </p>
      <div className="flex items-baseline gap-2 mt-1">
        <span className={`text-2xl font-semibold italic ${valueClass}`}>{value}</span>
        {unit && <span className="text-[10px] text-zinc-600 mono">{unit}</span>}
      </div>
    </div>
  )
}
