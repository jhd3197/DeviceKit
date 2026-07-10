import React from 'react'

/**
 * Sparkline — a tiny inline trend line (no axes), for device cards and table rows.
 * Feeds off the metrics-history sparkline endpoints (plan 08). Renders nothing until it
 * has at least two points so an empty history stays quiet.
 */
export default function Sparkline({
  values = [],
  color = '#10b981',
  width = 96,
  height = 24,
  strokeWidth = 1.25,
  fill = true,
  min,
  max,
}) {
  const data = (values || []).filter((v) => typeof v === 'number')
  if (data.length < 2) {
    return (
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width, height }} className="opacity-40">
        <line
          x1="0"
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="#3f3f46"
          strokeWidth="0.75"
          strokeDasharray="2 2"
        />
      </svg>
    )
  }

  const lo = min ?? Math.min(...data)
  const hi = max ?? Math.max(...data)
  const span = hi - lo || 1
  const pad = 2
  const plotH = height - pad * 2
  const n = data.length

  const toX = (i) => (i / (n - 1)) * width
  const toY = (v) => pad + plotH - ((v - lo) / span) * plotH

  let line = `M${toX(0).toFixed(2)},${toY(data[0]).toFixed(2)}`
  for (let i = 1; i < n; i++) line += ` L${toX(i).toFixed(2)},${toY(data[i]).toFixed(2)}`
  const area = `${line} L${width},${height} L0,${height} Z`

  const gradId = `spark-${color.replace('#', '')}-${n}`

  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width, height }} preserveAspectRatio="none">
      {fill && (
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
      )}
      {fill && <path d={area} fill={`url(#${gradId})`} />}
      <path d={line} fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinejoin="round" />
      <circle cx={toX(n - 1)} cy={toY(data[n - 1])} r="1.5" fill={color} />
    </svg>
  )
}
