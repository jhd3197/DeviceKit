import React, { useMemo, useState } from 'react'

/**
 * MetricChart — multi-series time-series line chart over a shared time + value domain.
 * Used by FleetMonitor and DeviceCompare (historical mode) to overlay several devices'
 * history for one metric (plan 08). Pure inline SVG (no chart library, per repo invariants).
 *
 * props.series: [{ id, label, color, points: [{ ts, value }] }]
 */
const PALETTE = ['#10b981', '#3b82f6', '#eab308', '#ef4444', '#a855f7', '#14b8a6']

export function seriesColor(i) {
  return PALETTE[i % PALETTE.length]
}

export default function MetricChart({
  series = [],
  height = 240,
  unit = '',
  yMin,
  yMax,
  valueFormat = (v) => `${Math.round(v)}${unit}`,
}) {
  const [hover, setHover] = useState(null) // {x, ts, rows:[{label,color,value}]}

  const W = 800
  const H = height
  const PAD_L = 44
  const PAD_R = 12
  const PAD_T = 12
  const PAD_B = 26
  const plotW = W - PAD_L - PAD_R
  const plotH = H - PAD_T - PAD_B

  const { tMin, tMax, vMin, vMax, hasData } = useMemo(() => {
    let tmin = Infinity
    let tmax = -Infinity
    let vmin = Infinity
    let vmax = -Infinity
    let any = false
    for (const s of series) {
      for (const p of s.points || []) {
        any = true
        if (p.ts < tmin) tmin = p.ts
        if (p.ts > tmax) tmax = p.ts
        if (p.value < vmin) vmin = p.value
        if (p.value > vmax) vmax = p.value
      }
    }
    if (!any) return { hasData: false }
    if (tmax === tmin) tmax = tmin + 1
    let lo = yMin ?? vmin
    let hi = yMax ?? vmax
    if (hi === lo) hi = lo + 1
    // A little headroom when the caller didn't pin the domain.
    if (yMax == null) hi += (hi - lo) * 0.08
    if (yMin == null) lo -= (hi - lo) * 0.04
    return { tMin: tmin, tMax: tmax, vMin: lo, vMax: hi, hasData: true }
  }, [series, yMin, yMax])

  if (!hasData) {
    return (
      <div
        className="flex items-center justify-center text-zinc-600 text-xs border border-main rounded-lg bg-[#020202]"
        style={{ height }}
      >
        No history yet for this metric &amp; period.
      </div>
    )
  }

  const toX = (ts) => PAD_L + ((ts - tMin) / (tMax - tMin)) * plotW
  const toY = (v) => PAD_T + plotH - ((v - vMin) / (vMax - vMin)) * plotH

  const yTicks = 4
  const gridVals = Array.from({ length: yTicks + 1 }, (_, i) => vMin + (i / yTicks) * (vMax - vMin))
  const xTicks = 4
  const timeVals = Array.from({ length: xTicks + 1 }, (_, i) => tMin + (i / xTicks) * (tMax - tMin))

  const fmtTime = (ts) => {
    const d = new Date(ts * 1000)
    const spanH = (tMax - tMin) / 3600
    if (spanH > 48) return `${d.getMonth() + 1}/${d.getDate()}`
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    if (px < PAD_L || px > W - PAD_R) {
      setHover(null)
      return
    }
    const ts = tMin + ((px - PAD_L) / plotW) * (tMax - tMin)
    const rows = []
    for (const s of series) {
      const pts = s.points || []
      if (!pts.length) continue
      let nearest = pts[0]
      for (const p of pts) if (Math.abs(p.ts - ts) < Math.abs(nearest.ts - ts)) nearest = p
      rows.push({ label: s.label, color: s.color, value: nearest.value })
    }
    setHover({ x: px, ts, rows })
  }

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full bg-[#020202] rounded-lg border border-main"
        style={{ height }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {/* Y grid + labels */}
        {gridVals.map((v, i) => {
          const y = toY(v)
          return (
            <g key={i}>
              <line x1={PAD_L} y1={y} x2={W - PAD_R} y2={y} stroke="#1f1f23" strokeWidth="0.5" />
              <text x={PAD_L - 6} y={y + 3} textAnchor="end" fill="#52525b" fontSize="9" fontFamily="monospace">
                {valueFormat(v)}
              </text>
            </g>
          )
        })}
        {/* X time labels */}
        {timeVals.map((ts, i) => (
          <text
            key={i}
            x={toX(ts)}
            y={H - 8}
            textAnchor={i === 0 ? 'start' : i === timeVals.length - 1 ? 'end' : 'middle'}
            fill="#52525b"
            fontSize="9"
            fontFamily="monospace"
          >
            {fmtTime(ts)}
          </text>
        ))}
        {/* Series */}
        {series.map((s) => {
          const pts = (s.points || []).filter((p) => typeof p.value === 'number')
          if (pts.length === 0) return null
          if (pts.length === 1) {
            return <circle key={s.id} cx={toX(pts[0].ts)} cy={toY(pts[0].value)} r="2.5" fill={s.color} />
          }
          let d = `M${toX(pts[0].ts).toFixed(2)},${toY(pts[0].value).toFixed(2)}`
          for (let i = 1; i < pts.length; i++) d += ` L${toX(pts[i].ts).toFixed(2)},${toY(pts[i].value).toFixed(2)}`
          return <path key={s.id} d={d} fill="none" stroke={s.color} strokeWidth="1.5" strokeLinejoin="round" />
        })}
        {/* Hover guideline */}
        {hover && (
          <line x1={hover.x} y1={PAD_T} x2={hover.x} y2={PAD_T + plotH} stroke="#3f3f46" strokeWidth="0.75" />
        )}
      </svg>
      {hover && hover.rows.length > 0 && (
        <div
          className="absolute top-2 pointer-events-none bg-zinc-900/95 border border-main rounded px-2 py-1.5 text-[10px] mono shadow-lg z-10"
          style={{ left: `${Math.min(80, (hover.x / W) * 100)}%` }}
        >
          <div className="text-zinc-500 mb-1">{new Date(hover.ts * 1000).toLocaleString()}</div>
          {hover.rows.map((r, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full" style={{ background: r.color }} />
              <span className="text-zinc-300 truncate max-w-[140px]">{r.label}</span>
              <span className="text-white ml-auto">{valueFormat(r.value)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
