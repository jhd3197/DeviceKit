import React, { useState, useEffect, useCallback, useRef } from 'react'
import { X, Plus, ChevronRight } from 'lucide-react'
import { api, subscribeToEvents } from '../api'

export default function DeviceCompare() {
  const [allDevices, setAllDevices] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [compareData, setCompareData] = useState([])
  const [pickValue, setPickValue] = useState('')
  const metricsHistories = useRef({}) // device_id -> [{time, cpu, mem, battery}]

  useEffect(() => {
    api.getDevices().then((res) => setAllDevices(res.devices || [])).catch(() => {})
  }, [])

  const fetchComparison = useCallback(async () => {
    if (selectedIds.length === 0) {
      setCompareData([])
      return
    }
    try {
      const res = await api.getFleetComparison(selectedIds)
      setCompareData(res.devices || [])
      // Push into histories
      for (const d of res.devices || []) {
        if (!metricsHistories.current[d.device_id]) {
          metricsHistories.current[d.device_id] = []
        }
        const hist = metricsHistories.current[d.device_id]
        hist.push({
          time: Date.now(),
          cpu: d.cpu_percent || 0,
          mem: d.ram_total_mb ? Math.round((d.ram_used_mb / d.ram_total_mb) * 100) : 0,
          battery: d.battery_level || 0,
        })
        if (hist.length > 60) hist.shift()
      }
    } catch {
      // silent
    }
  }, [selectedIds])

  useEffect(() => { fetchComparison() }, [fetchComparison])

  // SSE for real-time updates
  useEffect(() => {
    const es = subscribeToEvents({
      onDeviceState: (data) => {
        if (!selectedIds.includes(data.device_id)) return
        const metrics = data.state?.metrics
        if (!metrics) return
        setCompareData((prev) =>
          prev.map((d) =>
            d.device_id === data.device_id
              ? {
                  ...d,
                  cpu_percent: metrics.cpu_percent ?? d.cpu_percent,
                  battery_level: metrics.battery_level ?? d.battery_level,
                  ram_used_mb: metrics.ram_used_mb ?? d.ram_used_mb,
                  ram_total_mb: metrics.ram_total_mb ?? d.ram_total_mb,
                  temperature: metrics.battery_temperature ?? d.temperature,
                  is_charging: metrics.is_charging ?? d.is_charging,
                  online: true,
                }
              : d
          )
        )
        // Update history
        if (!metricsHistories.current[data.device_id]) {
          metricsHistories.current[data.device_id] = []
        }
        const hist = metricsHistories.current[data.device_id]
        hist.push({
          time: Date.now(),
          cpu: metrics.cpu_percent || 0,
          mem: metrics.ram_total_mb ? Math.round((metrics.ram_used_mb / metrics.ram_total_mb) * 100) : 0,
          battery: metrics.battery_level || 0,
        })
        if (hist.length > 60) hist.shift()
      },
    })
    return () => es.close()
  }, [selectedIds])

  const addDevice = () => {
    if (!pickValue || selectedIds.includes(pickValue) || selectedIds.length >= 4) return
    setSelectedIds((prev) => [...prev, pickValue])
    setPickValue('')
  }

  const removeDevice = (id) => {
    setSelectedIds((prev) => prev.filter((d) => d !== id))
    delete metricsHistories.current[id]
  }

  const available = allDevices.filter((d) => !selectedIds.includes(d.device_id))

  return (
    <>
      {/* Header */}
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-black/50 backdrop-blur-md shrink-0">
        <div className="flex items-center gap-2 text-xs font-medium text-zinc-500">
          <span>Fleet</span>
          <ChevronRight className="w-3 h-3" />
          <span className="text-zinc-200">Compare Devices</span>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-8 space-y-6 max-w-7xl">
        {/* Device picker */}
        <div className="flex items-center gap-3">
          <select
            value={pickValue}
            onChange={(e) => setPickValue(e.target.value)}
            className="bg-black border border-main px-3 py-2 text-xs rounded focus:outline-none w-64"
          >
            <option value="">Select a device...</option>
            {available.map((d) => (
              <option key={d.device_id} value={d.device_id}>
                {d.model || d.device_id} ({d.device_id})
              </option>
            ))}
          </select>
          <button
            onClick={addDevice}
            disabled={!pickValue || selectedIds.length >= 4}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded transition-colors flex items-center gap-2"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
          <span className="text-[10px] text-zinc-600">
            {selectedIds.length}/4 devices
          </span>
        </div>

        {selectedIds.length === 0 ? (
          <div className="flex items-center justify-center h-64 text-zinc-600 text-sm">
            Select up to 4 devices to compare side by side.
          </div>
        ) : (
          <div className={`grid gap-4 ${
            selectedIds.length === 1 ? 'grid-cols-1' :
            selectedIds.length === 2 ? 'grid-cols-2' :
            selectedIds.length === 3 ? 'grid-cols-3' : 'grid-cols-4'
          }`}>
            {compareData.map((d) => {
              const hist = metricsHistories.current[d.device_id] || []
              const memPercent = d.ram_total_mb ? Math.round((d.ram_used_mb / d.ram_total_mb) * 100) : 0
              return (
                <div key={d.device_id} className="bg-card border border-main rounded-xl p-4 space-y-4">
                  {/* Card header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold truncate">{d.model || d.device_id}</span>
                      <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${
                        d.online ? 'bg-emerald-500/10 text-emerald-400' : 'bg-zinc-700/50 text-zinc-500'
                      }`}>
                        {d.online ? 'ONLINE' : 'OFFLINE'}
                      </span>
                    </div>
                    <button
                      onClick={() => removeDevice(d.device_id)}
                      className="text-zinc-600 hover:text-white transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Charts */}
                  <StepChart
                    data={hist.map((h) => h.cpu)}
                    color="#10b981"
                    label="CPU"
                    currentValue={`${d.cpu_percent || 0}%`}
                  />
                  <StepChart
                    data={hist.map((h) => h.mem)}
                    color="#71717a"
                    label="RAM"
                    currentValue={`${(d.ram_used_mb / 1024).toFixed(1)}/${(d.ram_total_mb / 1024).toFixed(1)} GB`}
                  />
                  <StepChart
                    data={hist.map((h) => h.battery)}
                    color="#eab308"
                    label="Battery"
                    currentValue={`${d.battery_level || 0}%`}
                  />

                  {/* Diag rows */}
                  <div className="grid grid-cols-3 gap-3 pt-2">
                    <DiagRow label="Temp" value={`${d.temperature || 0}°C`} />
                    <DiagRow label="Battery" value={`${d.battery_level || 0}%`} />
                    <DiagRow label="Charging" value={d.is_charging ? 'Yes' : 'No'} />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </>
  )
}

function StepChart({ data, color, label, currentValue }) {
  const W = 300
  const H = 60
  const PAD_L = 24
  const PAD_R = 4
  const PAD_T = 4
  const PAD_B = 4
  const plotW = W - PAD_L - PAD_R
  const plotH = H - PAD_T - PAD_B
  const MAX_POINTS = 60

  const pts = data.length > 0 ? data : [0]
  const n = pts.length

  const toX = (i) => PAD_L + (n === 1 ? plotW : (i / (MAX_POINTS - 1)) * plotW)
  const toY = (v) => PAD_T + plotH - (Math.min(100, Math.max(0, v)) / 100) * plotH

  let linePath = ''
  let fillPath = ''
  if (n >= 1) {
    linePath = `M${toX(0)},${toY(pts[0])}`
    for (let i = 1; i < n; i++) {
      linePath += ` L${toX(i)},${toY(pts[i - 1])} L${toX(i)},${toY(pts[i])}`
    }
    fillPath = linePath + ` L${toX(n - 1)},${PAD_T + plotH} L${toX(0)},${PAD_T + plotH} Z`
  }

  const gradientId = `cmp-grad-${label.replace(/\s/g, '')}-${Math.random().toString(36).slice(2, 6)}`

  return (
    <div>
      <div className="flex justify-between text-[10px] mono mb-1">
        <span className="text-zinc-500 uppercase">{label}</span>
        <span className="text-white">{currentValue}</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full bg-[#020202] rounded border border-zinc-800/50"
        preserveAspectRatio="none"
        style={{ height: 70 }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1={PAD_L} y1={toY(50)} x2={W - PAD_R} y2={toY(50)} stroke="#27272a" strokeWidth="0.5" />
        {n >= 1 && <path d={fillPath} fill={`url(#${gradientId})`} />}
        {n >= 1 && <path d={linePath} fill="none" stroke={color} strokeWidth="1.5" />}
        {n >= 1 && (
          <>
            <circle cx={toX(n - 1)} cy={toY(pts[n - 1])} r="3" fill={color} opacity="0.3" />
            <circle cx={toX(n - 1)} cy={toY(pts[n - 1])} r="1.5" fill={color} />
          </>
        )}
      </svg>
    </div>
  )
}

function DiagRow({ label, value }) {
  return (
    <div className="flex justify-between border-b border-main pb-1">
      <span className="text-[10px] text-zinc-500 uppercase">{label}</span>
      <span className="text-[10px] font-semibold mono">{value || '--'}</span>
    </div>
  )
}
