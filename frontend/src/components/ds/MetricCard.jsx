import React from 'react'
import Sparkline from './Sparkline'

// Small labelled stat card used across dashboard widgets (fleet summary, fleet health).
// Extracted from Dashboard.jsx so widgets share one presentation primitive (plan 11).
// Pass `spark` (an array of values) to render a 24h trend line under the number.
export default function MetricCard({ label, value, unit, valueClass = '', spark, sparkColor = '#10b981' }) {
  return (
    <div className="bg-card border border-main p-4 rounded-lg">
      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
        {label}
      </p>
      <div className="flex items-baseline gap-2 mt-1">
        <span className={`text-2xl font-semibold ${valueClass}`}>{value}</span>
        {unit && <span className="text-[10px] text-zinc-600 mono">{unit}</span>}
      </div>
      {spark && spark.length >= 2 && (
        <div className="mt-2 -mb-1">
          <Sparkline values={spark} color={sparkColor} width={160} height={26} fluid />
        </div>
      )}
    </div>
  )
}
