import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, CheckCircle2, Copy, Loader2, Play, ShieldCheck, Square,
  TriangleAlert, Webhook, Workflow as WorkflowIcon,
} from 'lucide-react'
import { Canvas, RightRail, useWorkflow, deriveRunState } from '@tramo/editor/react'
import { createRegistry, BUILTIN_NODES } from '@tramo/spec'
import '@tramo/editor/styles.css'
import { api, subscribeToEvents } from '../api'

/**
 * Graph automation editor (plan 22 phase 6) — the embedded tramo editor over the
 * stored WorkflowDoc. The registry is tramo's builtins (filtered to what the Python
 * engine executes) ∪ the DeviceKit node pack served by the backend. Runs execute on
 * the backend; live per-node status streams in over SSE as tramo RunEvents and feeds
 * deriveRunState for on-canvas highlighting.
 */
export default function WorkflowEditor() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [pack, setPack] = useState(null)
  const [automation, setAutomation] = useState(null)
  const [flowRefs, setFlowRefs] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getNodePack().then(setPack).catch((e) => setError(e.message))
    api.getAutomation(id).then(setAutomation).catch((e) => setError(e.message))
    api.getAutomations()
      .then((r) => setFlowRefs(
        (r.automations || [])
          .filter((a) => a.id !== id)
          .map((a) => ({ id: a.id, name: a.name, description: a.description }))
      ))
      .catch(() => {})
  }, [id])

  if (error) {
    return (
      <div className="p-8 text-sm text-red-400">
        Failed to load workflow editor: {error}
      </div>
    )
  }
  if (!pack || !automation) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">
        <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading editor…
      </div>
    )
  }
  return (
    <GraphSurface
      id={id}
      pack={pack}
      automation={automation}
      flowRefs={flowRefs}
      onBack={() => navigate('/automations')}
    />
  )
}

function GraphSurface({ id, pack, automation, flowRefs, onBack }) {
  const [derived, setDerived] = useState(false)
  const [validation, setValidation] = useState(null)
  const [devices, setDevices] = useState([])
  const [selectedDevice, setSelectedDevice] = useState('')
  const [currentRun, setCurrentRun] = useState(null)
  const [runEvents, setRunEvents] = useState([])
  const [webhook, setWebhook] = useState(null)
  const [copied, setCopied] = useState(false)
  const runIdRef = useRef(null)

  const registry = useMemo(() => {
    const supported = new Set(pack.supported_builtins || [])
    const builtins = BUILTIN_NODES.filter((d) => supported.has(d.id))
    return createRegistry([...builtins, ...pack.nodes], [pack.integration])
  }, [pack])

  const loadDoc = useCallback(async () => {
    const r = await api.getAutomationGraph(id)
    setDerived(!!r.derived)
    return r.graph
  }, [id])

  const saveDoc = useCallback(async (doc) => {
    await api.saveAutomationGraph(id, doc)
    setDerived(false)
  }, [id])

  const workflow = useWorkflow({ loadDoc, saveDoc, registry, key: id })

  useEffect(() => {
    api.getDevices().then((r) => setDevices(r.devices || [])).catch(() => {})
  }, [])

  // Live run events (tramo RunEvent shapes broadcast by the backend engine).
  useEffect(() => {
    const es = subscribeToEvents({
      onAutomationRun: (event) => {
        if (event.run_id && event.run_id === runIdRef.current) {
          setRunEvents((prev) => [...prev, event])
        }
      },
    })
    return () => es.close()
  }, [])

  // Poll the run record for the authoritative terminal status.
  useEffect(() => {
    if (!currentRun || !['queued', 'running'].includes(currentRun.status)) return undefined
    const timer = setInterval(async () => {
      try {
        const run = await api.getAutomationRun(currentRun.id)
        setCurrentRun(run)
      } catch { /* transient */ }
    }, 1500)
    return () => clearInterval(timer)
  }, [currentRun])

  const runState = useMemo(() => deriveRunState(runEvents), [runEvents])
  const runResults = useMemo(() => {
    const out = {}
    for (const e of runEvents) {
      if (e.type === 'node-success') out[e.nodeId] = e.output
    }
    return out
  }, [runEvents])

  const hasWebhookTrigger = useMemo(
    () => (workflow.doc?.nodes || []).some((n) => n.type === 'webhook-trigger'),
    [workflow.doc]
  )

  const startRun = async () => {
    setValidation(null)
    setRunEvents([])
    const run = await api.runAutomation(id, selectedDevice || undefined)
    runIdRef.current = run.id
    setCurrentRun(run)
  }

  const cancelRun = async () => {
    if (currentRun) await api.cancelAutomationRun(currentRun.id)
  }

  const validate = async () => {
    const result = await api.validateAutomationGraph(id, workflow.doc)
    setValidation(result)
  }

  const showWebhook = async () => {
    let info = await api.getWebhookToken(id)
    if (!info.token) info = await api.createWebhookToken(id)
    setWebhook(info)
  }

  const copyWebhook = () => {
    if (!webhook?.url) return
    navigator.clipboard?.writeText(`${window.location.origin}${webhook.url}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const running = currentRun && ['queued', 'running'].includes(currentRun.status)

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-black workflow-editor">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-main bg-card shrink-0">
        <button onClick={onBack}
                className="p-1.5 rounded hover:bg-zinc-900 text-zinc-400">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <WorkflowIcon className="w-4 h-4 text-accent" />
        <div className="min-w-0">
          <div className="text-sm text-zinc-200 truncate">{automation.name}</div>
          <div className="text-[10px] uppercase tracking-widest text-zinc-500">
            Workflow graph
            {derived && (
              <span className="ml-2 text-amber-500 normal-case tracking-normal">
                derived from steps — first edit converts to a graph
              </span>
            )}
          </div>
        </div>

        <div className="flex-1" />

        {validation && (
          validation.ok ? (
            <span className="flex items-center gap-1 text-xs text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" /> Valid
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-red-400 max-w-md truncate"
                  title={(validation.errors || []).join('\n')}>
              <TriangleAlert className="w-3.5 h-3.5 shrink-0" />
              {(validation.errors || [])[0]}
            </span>
          )
        )}
        {currentRun && !running && (
          <span className={`text-xs ${currentRun.status === 'completed'
            ? 'text-emerald-400' : 'text-red-400'}`}>
            run {currentRun.status}
          </span>
        )}

        {hasWebhookTrigger && (
          <button onClick={showWebhook}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded border border-main text-zinc-300 hover:bg-zinc-900">
            <Webhook className="w-3.5 h-3.5" /> Webhook URL
          </button>
        )}
        <button onClick={validate}
                className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded border border-main text-zinc-300 hover:bg-zinc-900">
          <ShieldCheck className="w-3.5 h-3.5" /> Validate
        </button>

        <select value={selectedDevice}
                onChange={(e) => setSelectedDevice(e.target.value)}
                className="bg-card border border-main rounded px-2 py-1.5 text-xs text-zinc-300">
          <option value="">No device</option>
          {devices.map((d) => (
            <option key={d.serial || d.device_id} value={d.serial || d.device_id}>
              {d.model || d.serial || d.device_id}
            </option>
          ))}
        </select>
        {running ? (
          <button onClick={cancelRun}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded bg-red-600/90 hover:bg-red-600 text-white">
            <Square className="w-3.5 h-3.5" />
            {currentRun.status === 'queued' ? 'Queued…' : 'Cancel'}
          </button>
        ) : (
          <button onClick={startRun}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded bg-emerald-600 hover:bg-emerald-500 text-white">
            <Play className="w-3.5 h-3.5" /> Run
          </button>
        )}
      </div>

      {webhook && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-main bg-card-alt text-xs shrink-0">
          <Webhook className="w-3.5 h-3.5 text-violet-400" />
          <span className="text-zinc-500">POST</span>
          <code className="mono text-zinc-300">{webhook.url}</code>
          <button onClick={copyWebhook}
                  className="p-1 rounded hover:bg-zinc-900 text-zinc-400" title="Copy full URL">
            <Copy className="w-3 h-3" />
          </button>
          {copied && <span className="text-emerald-400">copied</span>}
          <span className="text-zinc-600">— the token is the auth; anyone with the URL can start runs</span>
          <button onClick={() => setWebhook(null)} className="ml-auto text-zinc-500 hover:text-zinc-300">
            dismiss
          </button>
        </div>
      )}

      {/* Canvas + inspector */}
      <div className="flex-1 flex min-h-0">
        <div className="flex-1 min-w-0">
          {workflow.ready ? (
            <Canvas workflow={workflow}
                    runStatus={runState.statuses}
                    runResults={runResults} />
          ) : (
            <div className="h-full flex items-center justify-center text-zinc-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading graph…
            </div>
          )}
        </div>
        <RightRail
          selection={workflow.selection}
          registry={registry}
          onApply={workflow.applyPatch}
          onClose={workflow.clearSelection}
          saveState={workflow.saveState}
          doc={workflow.doc}
          runResults={runResults}
          flowRefs={flowRefs}
        />
      </div>
    </div>
  )
}
