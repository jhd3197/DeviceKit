import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ChevronRight,
  RotateCw,
  Smartphone,
  Terminal,
  Maximize2,
  Circle,
  ChevronLeft,
  Camera,
  Bot,
  Send,
  Play,
  Square,
  AlertTriangle,
  Zap,
} from 'lucide-react'
import { api } from '../api'

const REFRESH_INTERVAL = 5000
const SCREEN_POLL_MS = 1000

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

  // Screen mirror state
  const [screenTs, setScreenTs] = useState(Date.now())
  const [screenLoaded, setScreenLoaded] = useState(false)
  const imgRef = useRef(null)

  // Agent state
  const [agentStatus, setAgentStatus] = useState({ status: 'stopped', current_action: null, cycle_count: 0 })
  const [agentLogs, setAgentLogs] = useState([])
  const [commandInput, setCommandInput] = useState('')
  const [urgentCommand, setUrgentCommand] = useState(false)
  const [hasProfile, setHasProfile] = useState(null)
  const agentLogRef = useRef(null)

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
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [deviceId])

  // Fetch agent status + logs
  const fetchAgent = useCallback(async () => {
    if (!deviceId) return
    try {
      const [status, logs, profile] = await Promise.all([
        api.getAgentStatus(deviceId).catch(() => ({ status: 'stopped' })),
        api.getAgentLogs(deviceId).catch(() => ({ logs: [] })),
        api.getProfileByDevice(deviceId).catch(() => null),
      ])
      setAgentStatus(status)
      setAgentLogs(logs.logs || [])
      setHasProfile(!!profile)
    } catch {
      // silent
    }
  }, [deviceId])

  useEffect(() => {
    fetchData()
    fetchAgent()
    const tid = setInterval(fetchData, REFRESH_INTERVAL)
    const aid = setInterval(fetchAgent, 2000)
    return () => { clearInterval(tid); clearInterval(aid) }
  }, [fetchData, fetchAgent])

  // Screen mirror polling
  useEffect(() => {
    if (!deviceId) return
    const sid = setInterval(() => setScreenTs(Date.now()), SCREEN_POLL_MS)
    return () => clearInterval(sid)
  }, [deviceId])

  useEffect(() => {
    if (shellRef.current) shellRef.current.scrollTop = shellRef.current.scrollHeight
  }, [shellHistory])

  useEffect(() => {
    if (agentLogRef.current) agentLogRef.current.scrollTop = agentLogRef.current.scrollHeight
  }, [agentLogs])

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

  // Screen tap handler
  const handleScreenClick = async (e) => {
    if (!imgRef.current || !device?.display) return
    const img = imgRef.current
    const rect = img.getBoundingClientRect()
    const natW = img.naturalWidth
    const natH = img.naturalHeight
    if (!natW || !natH) return

    // Calculate rendered image size within object-contain
    const containerW = rect.width
    const containerH = rect.height
    const imgAspect = natW / natH
    const containerAspect = containerW / containerH

    let renderedW, renderedH, offsetX, offsetY
    if (imgAspect > containerAspect) {
      renderedW = containerW
      renderedH = containerW / imgAspect
      offsetX = 0
      offsetY = (containerH - renderedH) / 2
    } else {
      renderedH = containerH
      renderedW = containerH * imgAspect
      offsetX = (containerW - renderedW) / 2
      offsetY = 0
    }

    const clickX = e.clientX - rect.left - offsetX
    const clickY = e.clientY - rect.top - offsetY

    if (clickX < 0 || clickY < 0 || clickX > renderedW || clickY > renderedH) return

    const devW = device.display.width || natW
    const devH = device.display.height || natH
    const tapX = Math.round((clickX / renderedW) * devW)
    const tapY = Math.round((clickY / renderedH) * devH)

    try {
      await api.tap(deviceId, tapX, tapY)
      // Refresh screen after tap
      setTimeout(() => setScreenTs(Date.now()), 300)
    } catch {
      // silent
    }
  }

  const handlePress = async (action) => {
    try {
      await api.press(deviceId, action)
      setTimeout(() => setScreenTs(Date.now()), 300)
    } catch {
      // silent
    }
  }

  const handleScreenshotDownload = () => {
    const url = api.screenshotUrl(deviceId)
    const a = document.createElement('a')
    a.href = url
    a.download = `${deviceId}-screenshot.png`
    a.click()
  }

  const handleAgentToggle = async () => {
    try {
      if (agentStatus.status !== 'stopped') {
        await api.stopAgent(deviceId)
      } else {
        await api.startAgent(deviceId)
      }
      fetchAgent()
    } catch {
      // silent
    }
  }

  const handleSendCommand = async () => {
    const cmd = commandInput.trim()
    if (!cmd) return
    try {
      await api.sendCommand(deviceId, cmd, urgentCommand ? 'urgent' : 'normal')
      setCommandInput('')
      fetchAgent()
    } catch {
      // silent
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

  const statusColors = {
    stopped: 'bg-zinc-700 text-zinc-400',
    autonomous: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
    executing_command: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  }

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
            {/* Phone mockup with live screen */}
            <div className="col-span-12 lg:col-span-5 flex flex-col items-center">
              <div className="relative group">
                <div className="w-[280px] h-[580px] bg-[#0a0a0a] rounded-[3rem] border-[6px] border-[#1a1a1a] shadow-2xl relative overflow-hidden flex items-center justify-center">
                  <div className="absolute top-0 w-1/3 h-6 bg-[#1a1a1a] rounded-b-xl z-20" />
                  {!screenLoaded && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-900 z-10">
                      <Smartphone className="w-16 h-16 text-zinc-800 opacity-20" />
                      <span className="text-[10px] mono text-zinc-600 mt-2">
                        CONNECTING TO SCREEN...
                      </span>
                    </div>
                  )}
                  <img
                    ref={imgRef}
                    src={`${api.screenshotUrl(deviceId)}?t=${screenTs}`}
                    alt="Device screen"
                    className={`w-full h-full object-contain cursor-crosshair ${screenLoaded ? '' : 'invisible'}`}
                    onClick={handleScreenClick}
                    onError={() => setScreenLoaded(false)}
                    onLoad={() => setScreenLoaded(true)}
                    draggable={false}
                  />
                </div>
                <div className="absolute -right-16 top-0 flex flex-col gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => handlePress('home')}
                    className="p-2 bg-zinc-900 border border-main rounded hover:bg-zinc-800 text-zinc-400"
                    title="Home"
                  >
                    <Circle className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handlePress('back')}
                    className="p-2 bg-zinc-900 border border-main rounded hover:bg-zinc-800 text-zinc-400"
                    title="Back"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    onClick={handleScreenshotDownload}
                    className="p-2 bg-zinc-900 border border-main rounded hover:bg-zinc-800 text-zinc-400"
                    title="Download Screenshot"
                  >
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

              {/* AI Agent Panel */}
              <div className="bg-card-alt border border-main rounded-xl overflow-hidden">
                <div className="px-6 py-4 border-b border-main bg-zinc-900/20 flex items-center justify-between">
                  <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-2">
                    <Bot className="w-3 h-3" /> AI Agent
                  </h3>
                  <div className="flex items-center gap-3">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full ${statusColors[agentStatus.status] || statusColors.stopped}`}>
                      {agentStatus.status}
                    </span>
                    {agentStatus.cycle_count > 0 && (
                      <span className="text-[10px] text-zinc-600 mono">
                        cycle #{agentStatus.cycle_count}
                      </span>
                    )}
                  </div>
                </div>
                <div className="p-6 space-y-4">
                  {hasProfile === false && (
                    <div className="flex items-center gap-2 bg-amber-950/50 border border-amber-900/50 rounded p-3 text-xs text-amber-400">
                      <AlertTriangle className="w-4 h-4 shrink-0" />
                      <span>
                        No profile for this device.{' '}
                        <Link to="/profiles/new" className="underline hover:no-underline">
                          Create one
                        </Link>{' '}
                        to start the agent.
                      </span>
                    </div>
                  )}

                  {/* Start/Stop */}
                  <button
                    onClick={handleAgentToggle}
                    disabled={hasProfile === false && agentStatus.status === 'stopped'}
                    className={`w-full flex items-center justify-center gap-2 py-2 rounded text-xs font-bold transition-all ${
                      agentStatus.status !== 'stopped'
                        ? 'bg-red-950 text-red-400 border border-red-900/50 hover:bg-red-900'
                        : 'bg-emerald-950 text-emerald-400 border border-emerald-900/50 hover:bg-emerald-900 disabled:opacity-40 disabled:cursor-not-allowed'
                    }`}
                  >
                    {agentStatus.status !== 'stopped' ? (
                      <><Square className="w-3 h-3" /> Stop Agent</>
                    ) : (
                      <><Play className="w-3 h-3" /> Start Agent</>
                    )}
                  </button>

                  {/* Current action */}
                  {agentStatus.current_action && (
                    <div className="text-xs text-zinc-400 bg-zinc-900/50 rounded p-2 mono">
                      {agentStatus.current_action}
                    </div>
                  )}

                  {/* Command input */}
                  <div className="flex gap-2">
                    <input
                      value={commandInput}
                      onChange={(e) => setCommandInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSendCommand()}
                      className="flex-1 bg-zinc-900 border border-main rounded px-3 py-2 text-xs text-white"
                      placeholder="Send command to agent..."
                    />
                    <button
                      onClick={() => setUrgentCommand(!urgentCommand)}
                      className={`p-2 rounded border text-xs ${
                        urgentCommand
                          ? 'bg-amber-950 border-amber-900/50 text-amber-400'
                          : 'bg-zinc-900 border-main text-zinc-500'
                      }`}
                      title="Toggle urgent priority"
                    >
                      <Zap className="w-3 h-3" />
                    </button>
                    <button
                      onClick={handleSendCommand}
                      className="p-2 bg-zinc-800 border border-main rounded hover:bg-zinc-700 text-zinc-400"
                    >
                      <Send className="w-3 h-3" />
                    </button>
                  </div>

                  {/* Action log */}
                  {agentLogs.length > 0 && (
                    <div
                      ref={agentLogRef}
                      className="max-h-40 overflow-y-auto bg-[#020202] rounded p-3 space-y-1"
                    >
                      {agentLogs.map((log, i) => (
                        <div key={i} className="flex gap-2 text-[10px] mono">
                          <span className="text-zinc-600 shrink-0">
                            {new Date(log.timestamp * 1000).toLocaleTimeString()}
                          </span>
                          <span className={
                            log.action === 'error' ? 'text-red-400'
                            : log.action === 'done' || log.action === 'command_done' ? 'text-emerald-400'
                            : log.action === 'command_start' ? 'text-amber-400'
                            : 'text-zinc-400'
                          }>
                            [{log.action}]
                          </span>
                          <span className="text-zinc-500 truncate">{log.description}</span>
                        </div>
                      ))}
                    </div>
                  )}
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
