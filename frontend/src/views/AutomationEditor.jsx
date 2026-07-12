import React, { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Plus,
  Save,
  ChevronUp,
  ChevronDown,
  Trash2,
  GripVertical,
  X,
  ArrowLeft,
  Copy,
  Download,
  Sparkles,
  Wand2,
  Check,
  XCircle,
  Loader,
  ChevronRight,
  Camera,
  Image,
  Eye,
  Crosshair,
} from 'lucide-react'
import { api } from '../api'

const CATEGORY_ORDER = ['Interaction', 'Apps', 'Timing', 'Debug', 'Visual']

export default function AutomationEditor() {
  const { id } = useParams()
  const navigate = useNavigate()
  const isNew = !id

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [steps, setSteps] = useState([])
  const [stepTypes, setStepTypes] = useState({})
  const [showPicker, setShowPicker] = useState(false)
  const [expandedStep, setExpandedStep] = useState(null)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(!isNew)

  // AI generation state
  const [aiOpen, setAiOpen] = useState(false)
  const [aiPrompt, setAiPrompt] = useState('')
  const [aiDeviceId, setAiDeviceId] = useState('')
  const [aiDevices, setAiDevices] = useState([])
  const [aiGenerating, setAiGenerating] = useState(false)
  const [aiPreview, setAiPreview] = useState(null) // { steps: [], explanation: '' }
  const [aiError, setAiError] = useState('')

  // Per-step refinement state
  const [refineStepId, setRefineStepId] = useState(null)
  const [refineInstruction, setRefineInstruction] = useState('')
  const [refining, setRefining] = useState(false)

  // Baseline state
  const [baselines, setBaselines] = useState([])
  const [baselineCapturing, setBaselineCapturing] = useState(null) // step index being captured
  const [baselineDevice, setBaselineDevice] = useState('')
  const [baselineDevices, setBaselineDevices] = useState([])
  const [baselinePreview, setBaselinePreview] = useState(null) // { stepIndex, imageUrl, baselineId }
  const [capturingBaseline, setCapturingBaseline] = useState(false)
  const [maskMode, setMaskMode] = useState(false)
  const [maskRegions, setMaskRegions] = useState([])
  const [maskStart, setMaskStart] = useState(null)

  useEffect(() => {
    api.getStepTypes().then(setStepTypes).catch(() => {})
  }, [])

  useEffect(() => {
    if (!isNew) {
      api
        .getAutomation(id)
        .then((a) => {
          setName(a.name || '')
          setDescription(a.description || '')
          setTags((a.tags || []).join(', '))
          setSteps(a.steps || [])
        })
        .catch((e) => console.error('Failed to load automation:', e))
        .finally(() => setLoading(false))
    }
  }, [id, isNew])

  // Fetch devices when AI panel opens
  useEffect(() => {
    if (aiOpen && aiDevices.length === 0) {
      api.getDevices().then((res) => {
        setAiDevices(res.devices || [])
      }).catch(() => {})
    }
  }, [aiOpen])

  // Fetch baselines when editing
  useEffect(() => {
    if (!isNew && id) {
      api.getBaselines(id).then((res) => setBaselines(res.baselines || [])).catch(() => {})
    }
  }, [id, isNew])

  // Fetch devices for baseline capture
  useEffect(() => {
    if (baselineCapturing !== null && baselineDevices.length === 0) {
      api.getDevices().then((res) => {
        const devs = res.devices || []
        setBaselineDevices(devs)
        if (devs.length > 0) setBaselineDevice(devs[0].device_id)
      }).catch(() => {})
    }
  }, [baselineCapturing])

  const addStep = (type) => {
    const typeDef = stepTypes[type] || {}
    const defaults = {}
    Object.entries(typeDef.config || {}).forEach(([key, schema]) => {
      if (schema.default !== undefined) defaults[key] = schema.default
      else if (schema.type === 'number') defaults[key] = 0
      else if (schema.type === 'select' && schema.options?.length)
        defaults[key] = schema.options[0]
      else defaults[key] = ''
    })
    const step = {
      id: crypto.randomUUID(),
      order: steps.length,
      type,
      config: defaults,
      label: typeDef.label || type,
    }
    setSteps((prev) => [...prev, step])
    setExpandedStep(step.id)
    setShowPicker(false)
  }

  const updateStepConfig = (stepId, key, value) => {
    setSteps((prev) =>
      prev.map((s) =>
        s.id === stepId ? { ...s, config: { ...s.config, [key]: value } } : s
      )
    )
  }

  const updateStepLabel = (stepId, label) => {
    setSteps((prev) => prev.map((s) => (s.id === stepId ? { ...s, label } : s)))
  }

  const removeStep = (stepId) => {
    setSteps((prev) =>
      prev
        .filter((s) => s.id !== stepId)
        .map((s, i) => ({ ...s, order: i }))
    )
    if (expandedStep === stepId) setExpandedStep(null)
  }

  const moveStep = (index, direction) => {
    const target = index + direction
    if (target < 0 || target >= steps.length) return
    setSteps((prev) => {
      const copy = [...prev]
      ;[copy[index], copy[target]] = [copy[target], copy[index]]
      return copy.map((s, i) => ({ ...s, order: i }))
    })
  }

  const handleSave = async () => {
    if (!name.trim()) return
    setSaving(true)
    const payload = {
      name: name.trim(),
      description: description.trim(),
      steps,
      tags: tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    }
    try {
      if (isNew) {
        await api.createAutomation(payload)
      } else {
        await api.updateAutomation(id, payload)
      }
      navigate('/automations')
    } catch (e) {
      console.error('Failed to save:', e)
    } finally {
      setSaving(false)
    }
  }

  const handleClone = async () => {
    try {
      const cloned = await api.cloneAutomation(id)
      navigate(`/automations/${cloned.id}/edit`)
    } catch (e) {
      console.error('Failed to clone:', e)
    }
  }

  const handleExport = async () => {
    try {
      const data = await api.exportAutomation(id)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${name || 'automation'}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Failed to export:', e)
    }
  }

  // AI generation
  const handleGenerate = async () => {
    if (!aiPrompt.trim()) return
    setAiGenerating(true)
    setAiError('')
    setAiPreview(null)
    try {
      const result = await api.generateSteps(aiPrompt.trim(), aiDeviceId || undefined)
      if (result.error) {
        setAiError(result.error)
      } else {
        setAiPreview(result)
      }
    } catch (e) {
      setAiError(e.message || 'Generation failed')
    } finally {
      setAiGenerating(false)
    }
  }

  const acceptAllGenerated = () => {
    if (!aiPreview?.steps) return
    const newSteps = aiPreview.steps.map((s, i) => ({
      id: crypto.randomUUID(),
      order: steps.length + i,
      type: s.type,
      config: s.config || {},
      label: s.label || s.type,
    }))
    setSteps((prev) => [...prev, ...newSteps])
    setAiPreview(null)
    setAiPrompt('')
  }

  const replaceAllGenerated = () => {
    if (!aiPreview?.steps) return
    const newSteps = aiPreview.steps.map((s, i) => ({
      id: crypto.randomUUID(),
      order: i,
      type: s.type,
      config: s.config || {},
      label: s.label || s.type,
    }))
    setSteps(newSteps)
    setAiPreview(null)
    setAiPrompt('')
  }

  const acceptSingleGenerated = (index) => {
    const s = aiPreview.steps[index]
    const step = {
      id: crypto.randomUUID(),
      order: steps.length,
      type: s.type,
      config: s.config || {},
      label: s.label || s.type,
    }
    setSteps((prev) => [...prev, step])
    setAiPreview((prev) => ({
      ...prev,
      steps: prev.steps.filter((_, i) => i !== index),
    }))
  }

  const rejectSingleGenerated = (index) => {
    setAiPreview((prev) => ({
      ...prev,
      steps: prev.steps.filter((_, i) => i !== index),
    }))
  }

  // Per-step refinement
  const handleRefine = async (step) => {
    if (!refineInstruction.trim()) return
    setRefining(true)
    try {
      const refined = await api.refineStep(step, refineInstruction.trim(), aiDeviceId || undefined)
      setSteps((prev) =>
        prev.map((s) =>
          s.id === step.id
            ? { ...s, type: refined.type || s.type, config: refined.config || s.config, label: refined.label || s.label }
            : s
        )
      )
      setRefineStepId(null)
      setRefineInstruction('')
    } catch (e) {
      console.error('Refinement failed:', e)
    } finally {
      setRefining(false)
    }
  }

  // Baseline capture
  const handleCaptureBaseline = async (stepIndex) => {
    if (!baselineDevice || !id) return
    setCapturingBaseline(true)
    try {
      const result = await api.createBaseline(id, {
        step_index: stepIndex,
        device_id: baselineDevice,
        label: steps[stepIndex]?.label || `Step ${stepIndex + 1} baseline`,
        mask_regions: maskRegions.length > 0 ? maskRegions : undefined,
      })
      setBaselines((prev) => [...prev, result])
      setBaselinePreview({
        stepIndex,
        imageUrl: api.getBaselineImageUrl(id, result.id),
        baselineId: result.id,
      })
      setBaselineCapturing(null)
      setMaskRegions([])
      // Auto-fill baseline_id in the step config if it's a screenshot_assert
      if (steps[stepIndex]?.type === 'screenshot_assert') {
        updateStepConfig(steps[stepIndex].id, 'baseline_id', result.id)
      }
    } catch (e) {
      console.error('Failed to capture baseline:', e)
    } finally {
      setCapturingBaseline(false)
    }
  }

  const handleDeleteBaseline = async (baselineId) => {
    if (!id) return
    try {
      await api.deleteBaseline(id, baselineId)
      setBaselines((prev) => prev.filter((b) => b.id !== baselineId))
      if (baselinePreview?.baselineId === baselineId) setBaselinePreview(null)
    } catch (e) {
      console.error('Failed to delete baseline:', e)
    }
  }

  const handleMaskMouseDown = (e) => {
    if (!maskMode) return
    const rect = e.currentTarget.getBoundingClientRect()
    setMaskStart({ x: e.clientX - rect.left, y: e.clientY - rect.top, rect })
  }

  const handleMaskMouseUp = (e) => {
    if (!maskMode || !maskStart) return
    const rect = maskStart.rect
    const endX = e.clientX - rect.left
    const endY = e.clientY - rect.top
    const x = Math.min(maskStart.x, endX)
    const y = Math.min(maskStart.y, endY)
    const w = Math.abs(endX - maskStart.x)
    const h = Math.abs(endY - maskStart.y)
    if (w > 5 && h > 5) {
      setMaskRegions((prev) => [...prev, { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) }])
    }
    setMaskStart(null)
  }

  // Group step types by category
  const grouped = {}
  Object.entries(stepTypes).forEach(([key, val]) => {
    const cat = val.category || 'Other'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push({ key, ...val })
  })

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">
        Loading...
      </div>
    )
  }

  return (
    <>
      {/* Header */}
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-body shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/automations')}
            className="text-zinc-400 hover:text-strong transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <h2 className="text-sm font-bold uppercase tracking-widest text-zinc-400">
            {isNew ? 'New Automation' : 'Edit Automation'}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {!isNew && (
            <>
              <button
                onClick={handleClone}
                className="border border-main text-zinc-400 hover:text-strong text-xs font-bold px-3 py-1.5 rounded transition-colors flex items-center gap-2"
              >
                <Copy className="w-3 h-3" /> Clone
              </button>
              <button
                onClick={handleExport}
                className="border border-main text-zinc-400 hover:text-strong text-xs font-bold px-3 py-1.5 rounded transition-colors flex items-center gap-2"
              >
                <Download className="w-3 h-3" /> Export JSON
              </button>
            </>
          )}
          <button
            onClick={handleSave}
            disabled={!name.trim() || saving}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2"
          >
            <Save className="w-3 h-3" /> {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Metadata */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Login Flow Test"
              className="w-full bg-body border border-main px-3 py-2 text-xs rounded focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
              Tags (comma separated)
            </label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="login, smoke"
              className="w-full bg-body border border-main px-3 py-2 text-xs rounded focus:outline-none"
            />
          </div>
        </div>
        <div>
          <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe what this automation does..."
            rows={2}
            className="w-full bg-body border border-main px-3 py-2 text-xs rounded focus:outline-none resize-none"
          />
        </div>

        {/* AI Generation Panel */}
        <div className="bg-card border border-main rounded overflow-hidden">
          <button
            onClick={() => setAiOpen(!aiOpen)}
            className="w-full flex items-center gap-3 px-4 py-3 hover:bg-zinc-900/30 transition-colors text-left"
          >
            <Sparkles className="w-4 h-4 text-amber-400 shrink-0" />
            <span className="text-xs font-bold text-zinc-300 flex-1">Generate with AI</span>
            <ChevronRight className={`w-4 h-4 text-zinc-500 transition-transform ${aiOpen ? 'rotate-90' : ''}`} />
          </button>

          {aiOpen && (
            <div className="px-4 pb-4 border-t border-main space-y-3 pt-3">
              <textarea
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                placeholder="Describe what the automation should do, e.g. &quot;Open Instagram, scroll feed, like 3 posts&quot;"
                rows={3}
                className="w-full bg-body border border-main px-3 py-2 text-xs rounded focus:outline-none resize-none"
              />
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
                    Device context (optional)
                  </label>
                  <select
                    value={aiDeviceId}
                    onChange={(e) => setAiDeviceId(e.target.value)}
                    className="w-full bg-body border border-main px-3 py-1.5 text-xs rounded focus:outline-none"
                  >
                    <option value="">No device context</option>
                    {aiDevices.map((d) => (
                      <option key={d.device_id} value={d.device_id}>
                        {d.name || d.device_id} ({d.device_id})
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  onClick={handleGenerate}
                  disabled={!aiPrompt.trim() || aiGenerating}
                  className="bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2 shrink-0"
                >
                  {aiGenerating ? (
                    <Loader className="w-3 h-3 animate-spin" />
                  ) : (
                    <Wand2 className="w-3 h-3" />
                  )}
                  Generate
                </button>
              </div>

              {aiError && (
                <div className="bg-red-500/10 border border-red-500/20 rounded p-3 text-xs text-red-400">
                  {aiError}
                </div>
              )}

              {/* Preview generated steps */}
              {aiPreview && aiPreview.steps?.length > 0 && (
                <div className="space-y-2">
                  {aiPreview.explanation && (
                    <p className="text-[10px] text-zinc-400 italic">{aiPreview.explanation}</p>
                  )}
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] font-bold text-zinc-500 uppercase">
                      Generated {aiPreview.steps.length} steps
                    </span>
                    <div className="flex-1" />
                    <button
                      onClick={acceptAllGenerated}
                      className="text-[10px] font-bold text-emerald-400 hover:text-emerald-300 transition-colors px-2 py-1 rounded border border-emerald-500/30 hover:border-emerald-500/60"
                    >
                      Accept All
                    </button>
                    <button
                      onClick={replaceAllGenerated}
                      className="text-[10px] font-bold text-amber-400 hover:text-amber-300 transition-colors px-2 py-1 rounded border border-amber-500/30 hover:border-amber-500/60"
                    >
                      Replace All
                    </button>
                  </div>
                  {aiPreview.steps.map((gs, gi) => (
                    <div
                      key={gi}
                      className="bg-body border border-amber-500/20 rounded p-3 flex items-center gap-3 text-xs"
                    >
                      <span className="text-[10px] bg-amber-900/40 text-amber-400 px-1.5 py-0.5 rounded uppercase font-bold shrink-0">
                        {gs.type}
                      </span>
                      <span className="flex-1 text-zinc-300 truncate">
                        {gs.label || JSON.stringify(gs.config)}
                      </span>
                      <button
                        onClick={() => acceptSingleGenerated(gi)}
                        className="p-1 text-emerald-500 hover:text-emerald-400 transition-colors"
                        title="Accept"
                      >
                        <Check className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => rejectSingleGenerated(gi)}
                        className="p-1 text-red-500 hover:text-red-400 transition-colors"
                        title="Reject"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {aiPreview && aiPreview.steps?.length === 0 && (
                <p className="text-[10px] text-zinc-500">All generated steps have been processed.</p>
              )}
            </div>
          )}
        </div>

        {/* Steps */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
              Steps ({steps.length})
            </h3>
            <button
              onClick={() => setShowPicker(true)}
              className="text-emerald-500 hover:text-emerald-400 text-xs font-bold flex items-center gap-1 transition-colors"
            >
              <Plus className="w-3 h-3" /> Add Step
            </button>
          </div>

          {steps.length === 0 ? (
            <div className="bg-card border border-main rounded p-8 text-center text-zinc-600 text-xs">
              No steps yet. Click "Add Step" or use "Generate with AI" above.
            </div>
          ) : (
            <div className="space-y-2">
              {steps.map((step, idx) => {
                const typeDef = stepTypes[step.type] || {}
                const isExpanded = expandedStep === step.id
                const isRefining = refineStepId === step.id
                return (
                  <div
                    key={step.id}
                    className="bg-card border border-main rounded overflow-hidden"
                  >
                    {/* Step header */}
                    <div
                      className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-zinc-900/30 transition-colors"
                      onClick={() =>
                        setExpandedStep(isExpanded ? null : step.id)
                      }
                    >
                      <GripVertical className="w-3 h-3 text-zinc-600 shrink-0" />
                      <span className="text-[10px] mono text-zinc-500 w-6 shrink-0">
                        {idx + 1}
                      </span>
                      <span className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded uppercase font-bold shrink-0">
                        {step.type}
                      </span>
                      <input
                        type="text"
                        value={step.label}
                        onChange={(e) => {
                          e.stopPropagation()
                          updateStepLabel(step.id, e.target.value)
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="flex-1 bg-transparent text-xs focus:outline-none text-zinc-300"
                        placeholder="Step label..."
                      />
                      <div className="flex items-center gap-1 shrink-0">
                        {step.type === 'screenshot_assert' && !isNew && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              setBaselineCapturing(idx)
                            }}
                            className="p-1 text-emerald-500 hover:text-emerald-400 transition-colors"
                            title="Capture Baseline"
                          >
                            <Camera className="w-3 h-3" />
                          </button>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setRefineStepId(isRefining ? null : step.id)
                            setRefineInstruction('')
                          }}
                          className="p-1 text-amber-500 hover:text-amber-400 transition-colors"
                          title="Refine with AI"
                        >
                          <Wand2 className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            moveStep(idx, -1)
                          }}
                          disabled={idx === 0}
                          className="p-1 text-zinc-500 hover:text-strong disabled:opacity-20 transition-colors"
                        >
                          <ChevronUp className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            moveStep(idx, 1)
                          }}
                          disabled={idx === steps.length - 1}
                          className="p-1 text-zinc-500 hover:text-strong disabled:opacity-20 transition-colors"
                        >
                          <ChevronDown className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            removeStep(step.id)
                          }}
                          className="p-1 text-zinc-500 hover:text-red-400 transition-colors"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>

                    {/* Inline AI refinement */}
                    {isRefining && (
                      <div className="px-4 py-2.5 border-t border-amber-500/20 bg-amber-500/5 flex items-center gap-2">
                        <Wand2 className="w-3 h-3 text-amber-400 shrink-0" />
                        <input
                          type="text"
                          value={refineInstruction}
                          onChange={(e) => setRefineInstruction(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleRefine(step)
                          }}
                          placeholder="e.g. change to swipe down, use resource ID instead..."
                          className="flex-1 bg-transparent text-xs focus:outline-none text-zinc-300 placeholder:text-zinc-600"
                          autoFocus
                        />
                        <button
                          onClick={() => handleRefine(step)}
                          disabled={!refineInstruction.trim() || refining}
                          className="text-[10px] font-bold text-amber-400 hover:text-amber-300 disabled:opacity-50 px-2 py-1 rounded border border-amber-500/30 transition-colors flex items-center gap-1"
                        >
                          {refining ? <Loader className="w-3 h-3 animate-spin" /> : 'Refine'}
                        </button>
                        <button
                          onClick={() => { setRefineStepId(null); setRefineInstruction('') }}
                          className="p-1 text-zinc-500 hover:text-strong transition-colors"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    )}

                    {/* Step config (expanded) */}
                    {isExpanded && Object.keys(typeDef.config || {}).length > 0 && (
                      <div className="px-4 py-3 border-t border-main bg-black/40 grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {Object.entries(typeDef.config).map(
                          ([configKey, schema]) => (
                            <div key={configKey}>
                              <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">
                                {schema.label || configKey}
                                {schema.required && (
                                  <span className="text-red-400 ml-0.5">*</span>
                                )}
                              </label>
                              {schema.type === 'select' ? (
                                <select
                                  value={step.config[configKey] || ''}
                                  onChange={(e) =>
                                    updateStepConfig(
                                      step.id,
                                      configKey,
                                      e.target.value
                                    )
                                  }
                                  className="w-full bg-body border border-main px-3 py-1.5 text-xs rounded focus:outline-none"
                                >
                                  {(schema.options || []).map((opt) => (
                                    <option key={opt} value={opt}>
                                      {opt}
                                    </option>
                                  ))}
                                </select>
                              ) : schema.type === 'number' ? (
                                <input
                                  type="number"
                                  value={step.config[configKey] ?? ''}
                                  onChange={(e) =>
                                    updateStepConfig(
                                      step.id,
                                      configKey,
                                      e.target.value === ''
                                        ? ''
                                        : Number(e.target.value)
                                    )
                                  }
                                  className="w-full bg-body border border-main px-3 py-1.5 text-xs rounded focus:outline-none"
                                />
                              ) : (
                                <input
                                  type="text"
                                  value={step.config[configKey] || ''}
                                  onChange={(e) =>
                                    updateStepConfig(
                                      step.id,
                                      configKey,
                                      e.target.value
                                    )
                                  }
                                  className="w-full bg-body border border-main px-3 py-1.5 text-xs rounded focus:outline-none"
                                />
                              )}
                            </div>
                          )
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

        {/* Visual Regression Baselines */}
        {!isNew && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-2">
                <Image className="w-3 h-3" /> Visual Baselines ({baselines.length})
              </h3>
            </div>

            {baselines.length === 0 ? (
              <div className="bg-card border border-main rounded p-4 text-center text-zinc-600 text-xs">
                No baselines yet. Use the <Camera className="w-3 h-3 inline" /> icon on screenshot_assert steps to capture baselines.
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {baselines.map((b) => (
                  <div key={b.id} className="bg-card border border-main rounded overflow-hidden group">
                    <div className="aspect-[9/16] bg-body relative cursor-pointer"
                      onClick={() => setBaselinePreview({ stepIndex: b.step_index, imageUrl: api.getBaselineImageUrl(id, b.id), baselineId: b.id })}
                    >
                      <img
                        src={api.getBaselineImageUrl(id, b.id)}
                        alt={b.label}
                        className="w-full h-full object-contain"
                      />
                      <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDeleteBaseline(b.id) }}
                          className="bg-black/70 rounded p-1 text-red-400 hover:text-red-300"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                    <div className="p-2">
                      <p className="text-[10px] text-zinc-300 truncate">{b.label}</p>
                      <p className="text-[8px] text-zinc-600 mono">
                        Step {b.step_index + 1} &middot; v{b.version} &middot; {b.device_model}
                        {b.mask_regions?.length > 0 && ` \u00b7 ${b.mask_regions.length} masks`}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Baseline capture dialog */}
        {baselineCapturing !== null && (
          <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
            <div className="bg-card border border-main rounded-lg w-full max-w-sm p-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-sm font-bold flex items-center gap-2">
                  <Camera className="w-4 h-4 text-emerald-400" /> Capture Baseline
                </h3>
                <button onClick={() => { setBaselineCapturing(null); setMaskRegions([]) }} className="text-zinc-500 hover:text-strong transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <p className="text-xs text-zinc-400 mb-4">
                Capture a screenshot from a device to use as the visual baseline for
                <span className="text-white font-medium"> step {baselineCapturing + 1}</span>.
              </p>
              <label className="block text-[10px] font-bold text-zinc-500 uppercase mb-1">Device</label>
              {baselineDevices.length === 0 ? (
                <p className="text-xs text-zinc-500 mb-4">No devices connected.</p>
              ) : (
                <select
                  value={baselineDevice}
                  onChange={(e) => setBaselineDevice(e.target.value)}
                  className="w-full bg-body border border-main px-3 py-2 text-xs rounded mb-4 focus:outline-none"
                >
                  {baselineDevices.map((d) => (
                    <option key={d.device_id} value={d.device_id}>
                      {d.name || d.device_id} ({d.device_id})
                    </option>
                  ))}
                </select>
              )}
              {maskRegions.length > 0 && (
                <div className="mb-3">
                  <p className="text-[10px] text-zinc-500 mb-1">{maskRegions.length} mask region(s) set</p>
                  <button
                    onClick={() => setMaskRegions([])}
                    className="text-[10px] text-red-400 hover:text-red-300"
                  >
                    Clear masks
                  </button>
                </div>
              )}
              <div className="flex justify-end gap-2">
                <button onClick={() => { setBaselineCapturing(null); setMaskRegions([]) }}
                  className="px-4 py-1.5 text-xs rounded border border-main text-zinc-400 hover:text-strong transition-colors">
                  Cancel
                </button>
                <button
                  onClick={() => handleCaptureBaseline(baselineCapturing)}
                  disabled={!baselineDevice || capturingBaseline}
                  className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2"
                >
                  {capturingBaseline ? <Loader className="w-3 h-3 animate-spin" /> : <Camera className="w-3 h-3" />}
                  Capture
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Baseline preview overlay */}
        {baselinePreview && (
          <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 cursor-pointer"
            onClick={() => setBaselinePreview(null)}>
            <div className="max-w-[90vw] max-h-[90vh] relative" onClick={(e) => e.stopPropagation()}>
              <img
                src={baselinePreview.imageUrl}
                alt="Baseline preview"
                className="max-w-full max-h-[85vh] rounded-lg border border-zinc-700 shadow-2xl"
                onMouseDown={handleMaskMouseDown}
                onMouseUp={handleMaskMouseUp}
              />
              <div className="absolute top-2 right-2 flex gap-2">
                <button
                  onClick={() => setMaskMode(!maskMode)}
                  className={`text-[10px] px-2 py-1 rounded flex items-center gap-1 transition-all ${
                    maskMode ? 'bg-amber-600 text-white' : 'bg-black/70 text-zinc-300 hover:text-strong'
                  }`}
                >
                  <Crosshair className="w-3 h-3" /> {maskMode ? 'Masking ON' : 'Add Masks'}
                </button>
                <button
                  onClick={() => setBaselinePreview(null)}
                  className="bg-black/70 text-zinc-300 hover:text-strong text-[10px] px-2 py-1 rounded"
                >
                  Close
                </button>
              </div>
              {maskMode && (
                <p className="absolute bottom-2 left-2 text-[9px] text-amber-300 bg-black/70 px-2 py-1 rounded">
                  Click and drag to mark ignore regions (clocks, ads, dynamic content)
                </p>
              )}
            </div>
          </div>
        )}

      {/* Step type picker overlay */}
      {showPicker && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-card border border-main rounded-lg w-full max-w-lg p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-sm font-bold">Add Step</h3>
              <button
                onClick={() => setShowPicker(false)}
                className="text-zinc-500 hover:text-strong transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {CATEGORY_ORDER.filter((c) => grouped[c]).map((category) => (
              <div key={category} className="mb-4">
                <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">
                  {category}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {grouped[category].map((st) => (
                    <button
                      key={st.key}
                      onClick={() => addStep(st.key)}
                      className="text-left bg-body border border-main rounded p-3 hover:border-emerald-600 hover:bg-zinc-900/30 transition-colors"
                    >
                      <p className="text-xs font-medium">{st.label}</p>
                      <p className="text-[10px] text-zinc-500 mono mt-0.5">
                        {st.key}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}
