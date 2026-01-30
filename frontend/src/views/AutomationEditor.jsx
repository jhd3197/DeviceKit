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
} from 'lucide-react'
import { api } from '../api'

const CATEGORY_ORDER = ['Interaction', 'Apps', 'Timing', 'Debug']

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
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-black shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/automations')}
            className="text-zinc-400 hover:text-white transition-colors"
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
                className="border border-main text-zinc-400 hover:text-white text-xs font-bold px-3 py-1.5 rounded transition-colors flex items-center gap-2"
              >
                <Copy className="w-3 h-3" /> Clone
              </button>
              <button
                onClick={handleExport}
                className="border border-main text-zinc-400 hover:text-white text-xs font-bold px-3 py-1.5 rounded transition-colors flex items-center gap-2"
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
              className="w-full bg-black border border-main px-3 py-2 text-xs rounded focus:outline-none"
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
              className="w-full bg-black border border-main px-3 py-2 text-xs rounded focus:outline-none"
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
            className="w-full bg-black border border-main px-3 py-2 text-xs rounded focus:outline-none resize-none"
          />
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
              No steps yet. Click "Add Step" to start building your automation.
            </div>
          ) : (
            <div className="space-y-2">
              {steps.map((step, idx) => {
                const typeDef = stepTypes[step.type] || {}
                const isExpanded = expandedStep === step.id
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
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            moveStep(idx, -1)
                          }}
                          disabled={idx === 0}
                          className="p-1 text-zinc-500 hover:text-white disabled:opacity-20 transition-colors"
                        >
                          <ChevronUp className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            moveStep(idx, 1)
                          }}
                          disabled={idx === steps.length - 1}
                          className="p-1 text-zinc-500 hover:text-white disabled:opacity-20 transition-colors"
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
                                  className="w-full bg-black border border-main px-3 py-1.5 text-xs rounded focus:outline-none"
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
                                  className="w-full bg-black border border-main px-3 py-1.5 text-xs rounded focus:outline-none"
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
                                  className="w-full bg-black border border-main px-3 py-1.5 text-xs rounded focus:outline-none"
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

      {/* Step type picker overlay */}
      {showPicker && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-card border border-main rounded-lg w-full max-w-lg p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-sm font-bold">Add Step</h3>
              <button
                onClick={() => setShowPicker(false)}
                className="text-zinc-500 hover:text-white transition-colors"
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
                      className="text-left bg-black border border-main rounded p-3 hover:border-emerald-600 hover:bg-zinc-900/30 transition-colors"
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
