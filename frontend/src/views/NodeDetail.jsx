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
  Home,
  ArrowLeft,
  Menu,
  Volume2,
  VolumeX,
  Power,
  ArrowUp,
  ArrowDown,
  Type,
  CornerUpLeft,
  Disc,
  MessageSquare,
  DollarSign,
  Trash2,
  ChevronDown,
  Cpu,
} from 'lucide-react'
import { api, subscribeToEvents } from '../api'

const REFRESH_INTERVAL = 30000
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

  // Drag/swipe gesture state
  const dragRef = useRef({ active: false, startX: 0, startY: 0, startTime: 0 })
  const [swipeTrail, setSwipeTrail] = useState(null) // {x1,y1,x2,y2} in px relative to img container

  // Agent state
  const [agentStatus, setAgentStatus] = useState({ status: 'stopped', current_action: null, cycle_count: 0 })
  const [agentLogs, setAgentLogs] = useState([])
  const [commandInput, setCommandInput] = useState('')
  const [urgentCommand, setUrgentCommand] = useState(false)
  const [hasProfile, setHasProfile] = useState(null)
  const agentLogRef = useRef(null)

  // Recording state
  const [recording, setRecording] = useState(false)
  const [recordingSessionId, setRecordingSessionId] = useState(null)
  const [recordedCount, setRecordedCount] = useState(0)

  // Prompture agent state
  const [agentUsage, setAgentUsage] = useState(null)
  const [conversationHistory, setConversationHistory] = useState([])
  const [showConversation, setShowConversation] = useState(false)
  const [showModelSelector, setShowModelSelector] = useState(false)
  const [modelInput, setModelInput] = useState('')

  const deviceId = id || ''

  // Metrics history for step charts (max 60 entries = ~5 min at 5s intervals)
  const metricsHistory = useRef([])

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

  // Fetch agent status + logs + usage
  const fetchAgent = useCallback(async () => {
    if (!deviceId) return
    try {
      const [status, logs, profile, usage] = await Promise.all([
        api.getAgentStatus(deviceId).catch(() => ({ status: 'stopped' })),
        api.getAgentLogs(deviceId).catch(() => ({ logs: [] })),
        api.getProfileByDevice(deviceId).catch(() => null),
        api.getAgentUsage(deviceId).catch(() => null),
      ])
      setAgentStatus(status)
      setAgentLogs(logs.logs || [])
      setHasProfile(!!profile)
      if (usage) setAgentUsage(usage)
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

  // SSE subscription for real-time device state
  useEffect(() => {
    const es = subscribeToEvents({
      onDeviceState: (data) => {
        if (data.device_id !== deviceId) return
        const metrics = data.state?.metrics
        if (metrics) {
          setDiagnostics(prev => ({
            ...prev,
            cpu_percent: metrics.cpu_percent,
            mem_used_mb: metrics.ram_used_mb,
            mem_total_mb: metrics.ram_total_mb,
            battery_level: metrics.battery_level,
            temperature: metrics.battery_temperature,
            is_charging: metrics.is_charging,
            network_type: metrics.network?.type,
            network_rx_rate: metrics.network?.rx_rate,
            network_tx_rate: metrics.network?.tx_rate,
            source: 'agent',
          }))
        }
      },
    })
    return () => es.close()
  }, [deviceId])

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

  // Keyboard shortcuts (only when not focused on an input)
  useEffect(() => {
    if (!deviceId) return
    const handler = (e) => {
      const tag = document.activeElement?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      const refresh = () => setTimeout(() => setScreenTs(Date.now()), 300)
      switch (e.key) {
        case 'h': e.preventDefault(); api.press(deviceId, 'home').then(refresh).catch(() => {}); break
        case 'b': e.preventDefault(); api.press(deviceId, 'back').then(refresh).catch(() => {}); break
        case 'r': e.preventDefault(); api.press(deviceId, 'recent').then(refresh).catch(() => {}); break
        case 'm': e.preventDefault(); api.press(deviceId, 'menu').then(refresh).catch(() => {}); break
        case 'Enter': e.preventDefault(); api.press(deviceId, 'enter').then(refresh).catch(() => {}); break
        case 'ArrowUp': e.preventDefault(); api.swipe(deviceId, 'up').then(refresh).catch(() => {}); break
        case 'ArrowDown': e.preventDefault(); api.swipe(deviceId, 'down').then(refresh).catch(() => {}); break
        case 'ArrowLeft': e.preventDefault(); api.swipe(deviceId, 'left').then(refresh).catch(() => {}); break
        case 'ArrowRight': e.preventDefault(); api.swipe(deviceId, 'right').then(refresh).catch(() => {}); break
        default: break
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [deviceId])

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

  // Map a mouse event to device coordinates; returns null if outside image area
  const mapToDevice = (e) => {
    if (!imgRef.current || !device?.display) return null
    const img = imgRef.current
    const rect = img.getBoundingClientRect()
    const natW = img.naturalWidth
    const natH = img.naturalHeight
    if (!natW || !natH) return null

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

    const px = e.clientX - rect.left - offsetX
    const py = e.clientY - rect.top - offsetY
    if (px < 0 || py < 0 || px > renderedW || py > renderedH) return null

    const devW = device.display.width || natW
    const devH = device.display.height || natH
    return {
      devX: Math.round((px / renderedW) * devW),
      devY: Math.round((py / renderedH) * devH),
      px: e.clientX - rect.left,
      py: e.clientY - rect.top,
    }
  }

  const SWIPE_THRESHOLD = 15 // px minimum drag distance to count as swipe

  const handleMouseDown = (e) => {
    e.preventDefault()
    const pt = mapToDevice(e)
    if (!pt) return
    dragRef.current = { active: true, startX: pt.devX, startY: pt.devY, startTime: Date.now(), px: pt.px, py: pt.py }
    setSwipeTrail(null)
  }

  const handleMouseMove = (e) => {
    if (!dragRef.current.active) return
    const img = imgRef.current
    if (!img) return
    const rect = img.getBoundingClientRect()
    const curPx = e.clientX - rect.left
    const curPy = e.clientY - rect.top
    const dx = curPx - dragRef.current.px
    const dy = curPy - dragRef.current.py
    if (Math.sqrt(dx * dx + dy * dy) > SWIPE_THRESHOLD) {
      setSwipeTrail({ x1: dragRef.current.px, y1: dragRef.current.py, x2: curPx, y2: curPy })
    }
  }

  const handleMouseUp = async (e) => {
    if (!dragRef.current.active) return
    dragRef.current.active = false
    const pt = mapToDevice(e)
    setSwipeTrail(null)

    if (!pt) return
    const { startX, startY } = dragRef.current
    const img = imgRef.current
    const rect = img.getBoundingClientRect()
    const pxDist = Math.sqrt(
      Math.pow(e.clientX - rect.left - dragRef.current.px, 2) +
      Math.pow(e.clientY - rect.top - dragRef.current.py, 2)
    )

    try {
      if (pxDist < SWIPE_THRESHOLD) {
        // Short drag = tap
        await api.tap(deviceId, startX, startY)
        recordIfActive({ type: 'tap', x: startX, y: startY })
      } else {
        // Long drag = swipe
        const elapsed = Date.now() - dragRef.current.startTime
        const duration = Math.max(200, Math.min(elapsed, 1500))
        await api.swipeCoords(deviceId, startX, startY, pt.devX, pt.devY, duration)
        // Determine direction from dominant axis
        const dx = pt.devX - startX
        const dy = pt.devY - startY
        let direction
        if (Math.abs(dx) > Math.abs(dy)) {
          direction = dx > 0 ? 'right' : 'left'
        } else {
          direction = dy > 0 ? 'down' : 'up'
        }
        recordIfActive({ type: 'swipe', direction, duration })
      }
      setTimeout(() => setScreenTs(Date.now()), 300)
    } catch {
      // silent
    }
  }

  const handleMouseLeave = () => {
    if (dragRef.current.active) {
      dragRef.current.active = false
      setSwipeTrail(null)
    }
  }

  const handlePress = async (action) => {
    try {
      await api.press(deviceId, action)
      recordIfActive({ type: 'press', key: action })
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

  const recordIfActive = async (actionData) => {
    if (!recording || !recordingSessionId) return
    try {
      const res = await api.recordAction(recordingSessionId, actionData)
      setRecordedCount(res.count || 0)
    } catch {
      // silent
    }
  }

  const handleRecordToggle = async () => {
    if (recording && recordingSessionId) {
      // Stop recording
      try {
        const res = await api.stopRecording(recordingSessionId)
        const steps = res.steps || []
        setRecording(false)
        setRecordingSessionId(null)
        setRecordedCount(0)
        if (steps.length > 0) {
          const automation = await api.createAutomation({
            name: `Recorded ${new Date().toLocaleString()}`,
            description: `Recorded from device ${deviceId}`,
            steps,
            tags: ['recorded'],
          })
          navigate(`/automations/${automation.id}/edit`)
        }
      } catch {
        setRecording(false)
        setRecordingSessionId(null)
        setRecordedCount(0)
      }
    } else {
      // Start recording
      try {
        const session = await api.startRecording(deviceId)
        setRecordingSessionId(session.id)
        setRecordedCount(0)
        setRecording(true)
      } catch {
        // silent
      }
    }
  }

  if (!deviceId) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-600 text-sm">
        Select a node from Fleet Overview to view details.
      </div>
    )
  }

  const cpuPercent = diagnostics?.cpu_percent ?? 0
  const memUsed = diagnostics?.mem_used_mb || 0
  const memTotal = diagnostics?.mem_total_mb || 1
  const memPercent = Math.round((memUsed / memTotal) * 100)
  const temp = diagnostics?.temperature || 0
  const battery = diagnostics?.battery_level || 0
  const uptimeSecs = diagnostics?.uptime_seconds || 0
  const uptimeStr = formatUptime(uptimeSecs)

  // Push metrics into history when diagnostics updates
  useEffect(() => {
    if (diagnostics) {
      const hist = metricsHistory.current
      hist.push({ time: Date.now(), cpu: cpuPercent, mem: memPercent, battery })
      if (hist.length > 60) hist.shift()
    }
  }, [diagnostics, cpuPercent, memPercent, battery])

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
            onClick={handleRecordToggle}
            className={`flex items-center gap-2 border px-3 py-1.5 rounded text-xs font-bold transition-all ${
              recording
                ? 'bg-red-950 border-red-900/50 text-red-400 hover:bg-red-900'
                : 'border-main text-zinc-400 hover:bg-zinc-900'
            }`}
          >
            <Disc className={`w-3 h-3 ${recording ? 'animate-pulse text-red-500' : ''}`} />
            {recording ? `Recording (${recordedCount})` : 'Record'}
          </button>
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
            {/* Phone mockup with side buttons */}
            <div className="col-span-12 lg:col-span-5 flex flex-col items-center gap-3">
              <div className="flex items-center gap-0">
                {/* Left side buttons (volume + power) */}
                <div className="flex flex-col gap-3 mr-1.5">
                  <SideButton icon={Volume2} label="Vol+" shortcut="" onClick={() => handlePress('volume_up')} />
                  <SideButton icon={VolumeX} label="Vol-" shortcut="" onClick={() => handlePress('volume_down')} />
                  <div className="h-4" />
                  <SideButton icon={Power} label="Power" shortcut="" onClick={() => handlePress('power')} />
                </div>

                {/* Phone frame */}
                <div className={`w-[260px] h-[560px] bg-black relative overflow-hidden flex items-center justify-center select-none shadow-2xl shadow-black/60 border-[3px] border-[#222] ${screenLoaded ? 'rounded-2xl' : 'rounded-[2.5rem]'} transition-all duration-300`}>
                  {!screenLoaded && (
                    <div className="absolute top-2 w-24 h-5 bg-[#111] rounded-full z-20" />
                  )}
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
                    className={`w-full h-full object-cover cursor-crosshair ${screenLoaded ? '' : 'invisible'}`}
                    onMouseDown={handleMouseDown}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={handleMouseLeave}
                    onError={() => setScreenLoaded(false)}
                    onLoad={() => setScreenLoaded(true)}
                    draggable={false}
                  />
                  {swipeTrail && (
                    <svg className="absolute inset-0 w-full h-full pointer-events-none z-30">
                      <line
                        x1={swipeTrail.x1} y1={swipeTrail.y1}
                        x2={swipeTrail.x2} y2={swipeTrail.y2}
                        stroke="rgba(16,185,129,0.7)" strokeWidth="3" strokeLinecap="round"
                      />
                      <circle cx={swipeTrail.x1} cy={swipeTrail.y1} r="4" fill="rgba(16,185,129,0.9)" />
                      <circle cx={swipeTrail.x2} cy={swipeTrail.y2} r="4" fill="white" />
                    </svg>
                  )}
                </div>

                {/* Right side buttons (swipe + screenshot) */}
                <div className="flex flex-col gap-3 ml-1.5">
                  <SideButton icon={ArrowUp} label="↑" shortcut="" onClick={() => { api.swipe(deviceId, 'up').catch(() => {}); setTimeout(() => setScreenTs(Date.now()), 400) }} />
                  <SideButton icon={ArrowDown} label="↓" shortcut="" onClick={() => { api.swipe(deviceId, 'down').catch(() => {}); setTimeout(() => setScreenTs(Date.now()), 400) }} />
                  <div className="h-4" />
                  <SideButton icon={Camera} label="Save" shortcut="" onClick={handleScreenshotDownload} />
                </div>
              </div>

              {/* Android nav bar */}
              <div className="flex gap-2 justify-center">
                {[
                  { icon: ArrowLeft, label: 'Back', key: 'B', action: 'back' },
                  { icon: Circle, label: 'Home', key: 'H', action: 'home' },
                  { icon: Square, label: 'Recent', key: 'R', action: 'recent' },
                ].map((btn) => (
                  <button
                    key={btn.action}
                    onClick={() => handlePress(btn.action)}
                    className="w-16 flex flex-col items-center gap-0.5 py-2 bg-zinc-900/80 border border-zinc-800 rounded-xl hover:bg-zinc-800 text-zinc-500 hover:text-white transition-all group"
                    title={`${btn.label} (${btn.key})`}
                  >
                    <btn.icon className="w-4 h-4" />
                    <span className="text-[8px] text-zinc-600 group-hover:text-zinc-400">{btn.key}</span>
                  </button>
                ))}
              </div>

              {/* Keyboard hint */}
              <p className="text-[9px] text-zinc-600 text-center">
                H home &middot; B back &middot; R recent &middot; M menu &middot; Arrow keys swipe &middot; Enter confirm
              </p>
            </div>

            {/* Right panels */}
            <div className="col-span-12 lg:col-span-7 space-y-6">
              {/* Live Diagnostics */}
              <div className="bg-card-alt border border-main rounded-xl p-6">
                <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-6">
                  Live Diagnostics
                </h3>
                <div className="space-y-4">
                  <StepChart
                    data={metricsHistory.current.map((d) => d.cpu)}
                    color="#10b981"
                    label="CPU Core Usage"
                    currentValue={`${cpuPercent}%`}
                  />
                  <StepChart
                    data={metricsHistory.current.map((d) => d.mem)}
                    color="#71717a"
                    label="RAM Occupancy"
                    currentValue={`${(memUsed / 1024).toFixed(1)}GB / ${(memTotal / 1024).toFixed(1)}GB`}
                  />
                  <StepChart
                    data={metricsHistory.current.map((d) => d.battery)}
                    color="#eab308"
                    label="Battery Level"
                    currentValue={`${battery}%${diagnostics?.is_charging ? ' (charging)' : ''}`}
                  />
                  <div className="grid grid-cols-3 gap-4 pt-2">
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
                    {agentStatus.model_name && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 mono">
                        <Cpu className="w-2.5 h-2.5 inline mr-1" />
                        {agentStatus.model_name.split('/').pop()}
                      </span>
                    )}
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

                  {/* Usage panel */}
                  {agentUsage && (agentUsage.call_count > 0 || agentUsage.total_tokens > 0) && (
                    <div className="bg-zinc-900/50 rounded p-3 space-y-2">
                      <div className="flex items-center gap-2 text-[10px] font-bold text-zinc-500 uppercase">
                        <DollarSign className="w-3 h-3" /> Usage
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-[10px] mono">
                        <div>
                          <span className="text-zinc-600">Prompt</span>
                          <p className="text-zinc-300">{(agentUsage.prompt_tokens || 0).toLocaleString()}</p>
                        </div>
                        <div>
                          <span className="text-zinc-600">Completion</span>
                          <p className="text-zinc-300">{(agentUsage.completion_tokens || 0).toLocaleString()}</p>
                        </div>
                        <div>
                          <span className="text-zinc-600">Cost</span>
                          <p className="text-emerald-400">${(agentUsage.total_cost || 0).toFixed(4)}</p>
                        </div>
                      </div>
                      <div className="flex gap-4 text-[10px] mono text-zinc-500">
                        <span>Calls: {agentUsage.call_count || 0}</span>
                        {agentUsage.errors > 0 && (
                          <span className="text-red-400">Errors: {agentUsage.errors}</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Model selector */}
                  <div className="relative">
                    <button
                      onClick={() => setShowModelSelector(!showModelSelector)}
                      className="w-full flex items-center justify-between bg-zinc-900 border border-main rounded px-3 py-2 text-xs text-zinc-400 hover:bg-zinc-800 transition-all"
                    >
                      <span className="flex items-center gap-2">
                        <Cpu className="w-3 h-3" />
                        {agentStatus.model_name || 'Select model...'}
                      </span>
                      <ChevronDown className="w-3 h-3" />
                    </button>
                    {showModelSelector && (
                      <div className="absolute top-full left-0 right-0 mt-1 bg-zinc-900 border border-main rounded shadow-lg z-10">
                        {[
                          'claude/claude-sonnet-4-20250514',
                          'openai/gpt-4o',
                          'groq/llama-3.1-70b-versatile',
                          'ollama/llama3.1:8b',
                          'google/gemini-2.0-flash',
                        ].map((m) => (
                          <button
                            key={m}
                            onClick={async () => {
                              try { await api.switchAgentModel(deviceId, m) } catch {}
                              setShowModelSelector(false)
                              fetchAgent()
                            }}
                            className="w-full text-left px-3 py-2 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-white transition-all mono"
                          >
                            {m}
                          </button>
                        ))}
                        <div className="flex border-t border-main">
                          <input
                            value={modelInput}
                            onChange={(e) => setModelInput(e.target.value)}
                            className="flex-1 bg-transparent px-3 py-2 text-xs text-white outline-none mono"
                            placeholder="Custom model..."
                          />
                          <button
                            onClick={async () => {
                              if (!modelInput.trim()) return
                              try { await api.switchAgentModel(deviceId, modelInput.trim()) } catch {}
                              setModelInput('')
                              setShowModelSelector(false)
                              fetchAgent()
                            }}
                            className="px-3 text-xs text-emerald-400 hover:text-emerald-300"
                          >
                            Apply
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Conversation history toggle + clear */}
                  <div className="flex gap-2">
                    <button
                      onClick={async () => {
                        if (!showConversation) {
                          try {
                            const res = await api.getConversationHistory(deviceId)
                            setConversationHistory(res.messages || [])
                          } catch {}
                        }
                        setShowConversation(!showConversation)
                      }}
                      className="flex-1 flex items-center justify-center gap-2 bg-zinc-900 border border-main rounded px-3 py-2 text-xs text-zinc-400 hover:bg-zinc-800 transition-all"
                    >
                      <MessageSquare className="w-3 h-3" />
                      {showConversation ? 'Hide' : 'Show'} Conversation ({conversationHistory.length})
                    </button>
                    <button
                      onClick={async () => {
                        try {
                          await api.clearConversation(deviceId)
                          setConversationHistory([])
                        } catch {}
                      }}
                      className="flex items-center gap-1 bg-zinc-900 border border-main rounded px-3 py-2 text-xs text-zinc-500 hover:text-red-400 hover:bg-zinc-800 transition-all"
                      title="Clear conversation memory"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>

                  {/* Conversation history */}
                  {showConversation && (
                    <div className="max-h-60 overflow-y-auto bg-[#020202] rounded p-3 space-y-2">
                      {conversationHistory.length === 0 ? (
                        <p className="text-[10px] text-zinc-600 text-center py-4">No conversation history yet.</p>
                      ) : (
                        conversationHistory.map((msg, i) => (
                          <div key={i} className={`text-[10px] p-2 rounded ${
                            msg.role === 'assistant'
                              ? 'bg-zinc-900 text-zinc-300'
                              : msg.role === 'user'
                              ? 'bg-zinc-800 text-zinc-400'
                              : 'bg-zinc-900/50 text-zinc-500'
                          }`}>
                            <span className="font-bold text-zinc-500 uppercase mr-2">
                              {msg.role || 'system'}
                            </span>
                            <span className="break-words">
                              {typeof msg.content === 'string'
                                ? msg.content.slice(0, 500)
                                : JSON.stringify(msg.content || '').slice(0, 500)}
                            </span>
                          </div>
                        ))
                      )}
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

function SideButton({ icon: Icon, label, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-9 h-9 flex flex-col items-center justify-center bg-zinc-900 border border-zinc-800 rounded-lg hover:bg-zinc-700 hover:border-zinc-600 text-zinc-500 hover:text-white transition-all"
      title={label}
    >
      <Icon className="w-3.5 h-3.5" />
    </button>
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

function StepChart({ data, color, label, currentValue }) {
  const W = 300
  const H = 80
  const PAD_L = 28
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

  // Build step polyline
  let linePath = ''
  let fillPath = ''
  if (n >= 1) {
    linePath = `M${toX(0)},${toY(pts[0])}`
    for (let i = 1; i < n; i++) {
      linePath += ` L${toX(i)},${toY(pts[i - 1])} L${toX(i)},${toY(pts[i])}`
    }
    fillPath = linePath + ` L${toX(n - 1)},${PAD_T + plotH} L${toX(0)},${PAD_T + plotH} Z`
  }

  const gridLines = [25, 50, 75]
  const gradientId = `grad-${label.replace(/\s/g, '')}`

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
        style={{ height: 100 }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Grid lines */}
        {gridLines.map((pct) => {
          const y = toY(pct)
          return (
            <g key={pct}>
              <line x1={PAD_L} y1={y} x2={W - PAD_R} y2={y} stroke="#27272a" strokeWidth="0.5" />
              <text x={PAD_L - 4} y={y + 3} textAnchor="end" fill="#52525b" fontSize="7" fontFamily="monospace">
                {pct}
              </text>
            </g>
          )
        })}
        {/* 0 and 100 labels */}
        <text x={PAD_L - 4} y={toY(0) + 3} textAnchor="end" fill="#52525b" fontSize="7" fontFamily="monospace">0</text>
        <text x={PAD_L - 4} y={toY(100) + 3} textAnchor="end" fill="#52525b" fontSize="7" fontFamily="monospace">100</text>
        {/* Fill under step line */}
        {n >= 1 && <path d={fillPath} fill={`url(#${gradientId})`} />}
        {/* Step line */}
        {n >= 1 && <path d={linePath} fill="none" stroke={color} strokeWidth="1.5" />}
        {/* Glowing end dot */}
        {n >= 1 && (
          <>
            <circle cx={toX(n - 1)} cy={toY(pts[n - 1])} r="4" fill={color} opacity="0.3" />
            <circle cx={toX(n - 1)} cy={toY(pts[n - 1])} r="2" fill={color} />
          </>
        )}
      </svg>
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
