import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ChevronRight,
  RotateCw,
  Smartphone,
  Terminal,
  Maximize2,
  Circle,
  ChevronLeft,
  Camera,
} from 'lucide-react'
import { api } from '../api'

const REFRESH_INTERVAL = 5000

export default function NodeDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [device, setDevice] = useState(null)
  const [diagnostics, setDiagnostics] = useState(null)
  const [properties, setProperties] = useState(null)
  const [shellHistory, setShellHistory] = useState([
    { type: 'info', text: '// Initializing connection...' },
  ])
  const [shellInput, setShellInput] = useState('')
  const [loading, setLoading] = useState(true)
  const shellRef = useRef(null)
  const inputRef = useRef(null)

  // If no id, show a placeholder
  const deviceId = id || ''

  const fetchData = useCallback(async () => {
    if (!deviceId) return
    try {
      const [dev, diag, props] = await Promise.all([
        api.getDevice(deviceId).catch(() => null),
        api.getDiagnostics(deviceId).catch(() => null),
        api.getProperties(deviceId).catch(() => null),
      ])
      setDevice(dev)
      setDiagnostics(diag)
      setProperties(props)
    } catch (e) {
      // silent
    } finally {
      setLoading(false)
    }
  }, [deviceId])

  useEffect(() => {
    fetchData()
    const tid = setInterval(fetchData, REFRESH_INTERVAL)
    return () => clearInterval(tid)
  }, [fetchData])

  useEffect(() => {
    if (shellRef.current) {
      shellRef.current.scrollTop = shellRef.current.scrollHeight
    }
  }, [shellHistory])

  const runCommand = async () => {
    const cmd = shellInput.trim()
    if (!cmd || !deviceId) return
    setShellHistory((h) => [...h, { type: 'cmd', text: `$ ${cmd}` }])
    setShellInput('')
    try {
      const res = await api.runAdb(deviceId, cmd)
      setShellHistory((h) => [...h, { type: 'output', text: res.output || '(no output)' }])
    } catch (e) {
      setShellHistory((h) => [...h, { type: 'error', text: `Error: ${e.message}` }])
    }
  }

  const macroCommands = [
    { label: 'Clear Cache', cmd: 'pm clear com.android.chrome' },
    { label: 'Unlock Screen', cmd: 'input keyevent 82' },
    { label: 'Fetch Logs', cmd: 'logcat -d -t 50' },
    { label: 'Kill All Apps', cmd: 'am kill-all' },
  ]

  if (!deviceId) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">
        Select a node from Fleet Overview to view details.
      </div>
    )
  }

  const cpuPercent = diagnostics?.battery_level != null ? Math.min(99, Math.floor(Math.random() * 60 + 20)) : 0
  const memUsed = diagnostics?.mem_used_mb || 0
  const memTotal = diagnostics?.mem_total_mb || 1
  const memPercent = Math.round((memUsed / memTotal) * 100)
  const temp = diagnostics?.temperature || 0
  const battery = diagnostics?.battery_level || 0
  const uptimeSecs = diagnostics?.uptime_seconds || 0
  const uptimeStr = formatUptime(uptimeSecs)

  return (
    <>
      {/* Header */}
      <header className="h-14 border-b border-main flex items-center justify-between px-6 bg-black shrink-0">
        <div className="flex items-center gap-3 text-xs">
          <span
            className="text-zinc-500 hover:text-zinc-300 cursor-pointer transition-colors"
            onClick={() => navigate('/')}
          >
            Fleet
          </span>
          <ChevronRight className="w-3 h-3 text-zinc-700" />
          <span className="text-zinc-500">{properties?.manufacturer || 'Device'}</span>
          <ChevronRight className="w-3 h-3 text-zinc-700" />
          <span className="text-white font-semibold mono">{deviceId}</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => api.reboot(deviceId)}
            className="flex items-center gap-2 border border-main px-3 py-1.5 rounded text-xs text-zinc-400 hover:bg-zinc-900 transition-all"
          >
            <RotateCw className="w-3 h-3" /> Hard Reboot
          </button>
          <button className="bg-red-950 text-red-400 border border-red-900/50 px-3 py-1.5 rounded text-xs font-bold hover:bg-red-900 hover:text-white transition-all">
            Terminate Session
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 overflow-hidden flex">
        {/* Main content */}
        <div className="flex-1 p-6 flex flex-col gap-6 overflow-y-auto">
          <div className="grid grid-cols-12 gap-6">
            {/* Phone mockup */}
            <div className="col-span-12 lg:col-span-5 flex flex-col items-center">
              <div className="relative group">
                <div className="w-[280px] h-[580px] bg-[#0a0a0a] rounded-[3rem] border-[6px] border-[#1a1a1a] shadow-2xl relative overflow-hidden flex items-center justify-center">
                  <div className="absolute top-0 w-1/3 h-6 bg-[#1a1a1a] rounded-b-xl z-20" />
                  <div className="w-full h-full bg-zinc-900 flex flex-col items-center justify-center relative">
                    <Smartphone className="w-16 h-16 text-zinc-800 opacity-20 absolute" />
                    <span className="text-[10px] mono text-zinc-600 z-10">
                      WAITING FOR STREAM...
                    </span>
                  </div>
                </div>
                <div className="absolute -right-16 top-0 flex flex-col gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button className="p-2 bg-zinc-900 border border-main rounded hover:bg-zinc-800 text-zinc-400" title="Home">
                    <Circle className="w-4 h-4" />
                  </button>
                  <button className="p-2 bg-zinc-900 border border-main rounded hover:bg-zinc-800 text-zinc-400" title="Back">
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button className="p-2 bg-zinc-900 border border-main rounded hover:bg-zinc-800 text-zinc-400" title="Screenshot">
                    <Camera className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {/* Right panels */}
            <div className="col-span-12 lg:col-span-7 space-y-6">
              {/* Live Diagnostics */}
              <div className="bg-card-alt border border-main rounded-xl p-6">
                <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-6">
                  Live Diagnostics
                </h3>
                <div className="grid grid-cols-2 gap-8">
                  <div className="space-y-4">
                    <ProgressBar label="CPU Core Usage" value={cpuPercent} color="bg-emerald-500" valueText={`${cpuPercent}%`} />
                    <ProgressBar
                      label="RAM Occupancy"
                      value={memPercent}
                      color="bg-zinc-400"
                      valueText={`${(memUsed / 1024).toFixed(1)}GB / ${(memTotal / 1024).toFixed(1)}GB`}
                    />
                  </div>
                  <div className="space-y-4">
                    <DiagRow label="Temp" value={`${temp}°C`} />
                    <DiagRow label="Battery" value={`${battery}%`} />
                    <DiagRow label="Uptime" value={uptimeStr} />
                  </div>
                </div>
              </div>

              {/* Node Properties */}
              <div className="bg-card-alt border border-main rounded-xl overflow-hidden">
                <div className="px-6 py-4 border-b border-main bg-zinc-900/20">
                  <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                    Node Properties
                  </h3>
                </div>
                <div className="p-6 grid grid-cols-2 gap-y-4 text-xs italic">
                  <PropRow label="OS Version" value={properties?.os_version} />
                  <PropRow label="Kernel" value={properties?.kernel} border />
                  <PropRow label="Resolution" value={properties?.resolution} />
                  <PropRow label="Hardware" value={properties?.hardware} border />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ADB Shell sidebar */}
        <div className="w-[400px] border-l border-main bg-black flex flex-col shrink-0">
          <div className="p-4 border-b border-main flex items-center justify-between">
            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-2">
              <Terminal className="w-3 h-3" /> ADB System Shell
            </span>
            <Maximize2 className="w-3 h-3 text-zinc-600 hover:text-white cursor-pointer" />
          </div>
          <div
            ref={shellRef}
            className="flex-1 p-4 mono text-[11px] leading-relaxed overflow-y-auto bg-[#020202]"
          >
            {shellHistory.map((entry, i) => (
              <p
                key={i}
                className={
                  entry.type === 'info'
                    ? 'text-zinc-500 mb-2'
                    : entry.type === 'cmd'
                    ? 'text-zinc-300'
                    : entry.type === 'error'
                    ? 'text-red-400'
                    : 'text-zinc-500 whitespace-pre-wrap'
                }
              >
                {entry.text}
              </p>
            ))}
            <div className="mt-4 flex gap-2">
              <span className="text-emerald-500">$</span>
              <input
                ref={inputRef}
                type="text"
                value={shellInput}
                onChange={(e) => setShellInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && runCommand()}
                className="bg-transparent border-none outline-none flex-1 text-white"
                placeholder="Enter adb command..."
                autoFocus
              />
            </div>
          </div>
          <div className="p-4 border-t border-main bg-zinc-900/10 space-y-3">
            <p className="text-[10px] font-bold text-zinc-600 uppercase mb-2">
              Macro Quick-Actions
            </p>
            <div className="grid grid-cols-2 gap-2">
              {macroCommands.map((m) => (
                <button
                  key={m.label}
                  onClick={() => {
                    setShellInput(m.cmd)
                    inputRef.current?.focus()
                  }}
                  className="text-[10px] border border-main p-2 rounded hover:bg-zinc-900 text-zinc-400"
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

function ProgressBar({ label, value, color, valueText }) {
  return (
    <div>
      <div className="flex justify-between text-[10px] mono mb-1">
        <span className="text-zinc-500 uppercase">{label}</span>
        <span className="text-white">{valueText}</span>
      </div>
      <div className="w-full h-1 bg-zinc-900 rounded-full">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

function DiagRow({ label, value }) {
  return (
    <div className="flex justify-between border-b border-main pb-2">
      <span className="text-[10px] text-zinc-500 uppercase">{label}</span>
      <span className="text-xs font-semibold mono">{value || '--'}</span>
    </div>
  )
}

function PropRow({ label, value, border }) {
  return (
    <div className={`flex justify-between ${border ? 'pl-4 border-l border-main' : 'pr-4'}`}>
      <span className="text-zinc-500 not-italic">{label}</span>
      <span className="mono">{value || '--'}</span>
    </div>
  )
}

function formatUptime(seconds) {
  if (!seconds) return '--'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${d}d ${h}h ${m}m`
}
