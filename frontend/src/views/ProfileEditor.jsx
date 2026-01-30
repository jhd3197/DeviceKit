import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Save, ArrowLeft, X, Plus } from 'lucide-react'
import { api } from '../api'

const DEFAULT_BEHAVIOR = {
  scroll_speed: 'medium',
  engagement_rate: 0.5,
  session_duration_min: 30,
  break_between_sessions_min: 15,
}

export default function ProfileEditor() {
  const { id } = useParams()
  const navigate = useNavigate()
  const isEdit = !!id

  const [devices, setDevices] = useState([])
  const [form, setForm] = useState({
    device_id: '',
    name: '',
    personality: '',
    niche: '',
    interests: [],
    behavior_patterns: { ...DEFAULT_BEHAVIOR },
    apps: [],
    model_name: '',
  })
  const [interestInput, setInterestInput] = useState('')
  const [appInput, setAppInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getDevices().then((r) => setDevices(r.devices || [])).catch(() => {})
    if (isEdit) {
      api.getProfile(id).then((p) => {
        if (p) setForm({
          device_id: p.device_id || '',
          name: p.name || '',
          personality: p.personality || '',
          niche: p.niche || '',
          interests: p.interests || [],
          behavior_patterns: { ...DEFAULT_BEHAVIOR, ...p.behavior_patterns },
          apps: p.apps || [],
          model_name: p.model_name || '',
        })
      }).catch(() => setError('Profile not found'))
    }
  }, [id, isEdit])

  const set = (key, val) => setForm((f) => ({ ...f, [key]: val }))
  const setBehavior = (key, val) =>
    setForm((f) => ({ ...f, behavior_patterns: { ...f.behavior_patterns, [key]: val } }))

  const addInterest = () => {
    const t = interestInput.trim()
    if (t && !form.interests.includes(t)) {
      set('interests', [...form.interests, t])
    }
    setInterestInput('')
  }

  const removeInterest = (i) => set('interests', form.interests.filter((_, idx) => idx !== i))

  const addApp = () => {
    const t = appInput.trim()
    if (t) {
      set('apps', [...form.apps, { package: t, priority: 'normal' }])
    }
    setAppInput('')
  }

  const removeApp = (i) => set('apps', form.apps.filter((_, idx) => idx !== i))

  const handleSave = async () => {
    if (!form.device_id || !form.name) {
      setError('Device and name are required')
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (isEdit) {
        await api.updateProfile(id, form)
      } else {
        await api.createProfile(form)
      }
      navigate('/profiles')
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <header className="h-14 border-b border-main flex items-center justify-between px-6 bg-black shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/profiles')} className="text-zinc-500 hover:text-white">
            <ArrowLeft className="w-4 h-4" />
          </button>
          <h1 className="text-sm font-bold">{isEdit ? 'Edit Profile' : 'New Profile'}</h1>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 bg-white text-black px-4 py-1.5 rounded text-xs font-bold hover:bg-zinc-200 transition-all disabled:opacity-50"
        >
          <Save className="w-3 h-3" /> {saving ? 'Saving...' : 'Save'}
        </button>
      </header>

      <div className="flex-1 p-6 overflow-y-auto">
        <div className="max-w-2xl mx-auto space-y-6">
          {error && (
            <div className="bg-red-950 border border-red-900/50 text-red-400 text-xs p-3 rounded">
              {error}
            </div>
          )}

          {/* Device & Name */}
          <div className="bg-card-alt border border-main rounded-xl p-6 space-y-4">
            <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Basic Info</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Device</label>
                <select
                  value={form.device_id}
                  onChange={(e) => set('device_id', e.target.value)}
                  className="w-full bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white"
                >
                  <option value="">Select device...</option>
                  {devices.map((d) => (
                    <option key={d.device_id} value={d.device_id}>
                      {d.name || d.device_id}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Profile Name</label>
                <input
                  value={form.name}
                  onChange={(e) => set('name', e.target.value)}
                  className="w-full bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white"
                  placeholder="e.g. Alex the Fitness Guru"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Niche</label>
              <input
                value={form.niche}
                onChange={(e) => set('niche', e.target.value)}
                className="w-full bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white"
                placeholder="e.g. fitness, cooking, tech"
              />
            </div>
          </div>

          {/* AI Model */}
          <div className="bg-card-alt border border-main rounded-xl p-6 space-y-4">
            <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">AI Model</h3>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">LLM Model (provider/model format)</label>
              <select
                value={[
                  'claude/claude-sonnet-4-20250514',
                  'openai/gpt-4o',
                  'groq/llama-3.1-70b-versatile',
                  'ollama/llama3.1:8b',
                  'google/gemini-2.0-flash',
                ].includes(form.model_name) ? form.model_name : '__custom__'}
                onChange={(e) => {
                  if (e.target.value !== '__custom__') set('model_name', e.target.value)
                }}
                className="w-full bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white"
              >
                <option value="">Default (from server config)</option>
                <option value="claude/claude-sonnet-4-20250514">claude/claude-sonnet-4-20250514</option>
                <option value="openai/gpt-4o">openai/gpt-4o</option>
                <option value="groq/llama-3.1-70b-versatile">groq/llama-3.1-70b-versatile</option>
                <option value="ollama/llama3.1:8b">ollama/llama3.1:8b</option>
                <option value="google/gemini-2.0-flash">google/gemini-2.0-flash</option>
                <option value="__custom__">Custom...</option>
              </select>
            </div>
            {![
              '', 'claude/claude-sonnet-4-20250514', 'openai/gpt-4o',
              'groq/llama-3.1-70b-versatile', 'ollama/llama3.1:8b', 'google/gemini-2.0-flash',
            ].includes(form.model_name) && (
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Custom Model Name</label>
                <input
                  value={form.model_name}
                  onChange={(e) => set('model_name', e.target.value)}
                  className="w-full bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white mono"
                  placeholder="provider/model-name"
                />
              </div>
            )}
          </div>

          {/* Personality */}
          <div className="bg-card-alt border border-main rounded-xl p-6 space-y-4">
            <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Personality</h3>
            <textarea
              value={form.personality}
              onChange={(e) => set('personality', e.target.value)}
              rows={4}
              className="w-full bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white resize-none"
              placeholder="Describe this persona's personality, how they browse, what they engage with..."
            />
          </div>

          {/* Interests */}
          <div className="bg-card-alt border border-main rounded-xl p-6 space-y-4">
            <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Interests</h3>
            <div className="flex gap-2">
              <input
                value={interestInput}
                onChange={(e) => setInterestInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addInterest())}
                className="flex-1 bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white"
                placeholder="Add an interest..."
              />
              <button onClick={addInterest} className="p-2 bg-zinc-800 border border-main rounded hover:bg-zinc-700">
                <Plus className="w-4 h-4" />
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {form.interests.map((interest, i) => (
                <span key={i} className="flex items-center gap-1 bg-zinc-800 border border-main px-2 py-1 rounded text-xs">
                  {interest}
                  <button onClick={() => removeInterest(i)} className="text-zinc-500 hover:text-red-400">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>

          {/* Behavior */}
          <div className="bg-card-alt border border-main rounded-xl p-6 space-y-4">
            <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Behavior Patterns</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Scroll Speed</label>
                <select
                  value={form.behavior_patterns.scroll_speed}
                  onChange={(e) => setBehavior('scroll_speed', e.target.value)}
                  className="w-full bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white"
                >
                  <option value="slow">Slow</option>
                  <option value="medium">Medium</option>
                  <option value="fast">Fast</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">
                  Engagement Rate: {Math.round(form.behavior_patterns.engagement_rate * 100)}%
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={form.behavior_patterns.engagement_rate}
                  onChange={(e) => setBehavior('engagement_rate', parseFloat(e.target.value))}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Session Duration (min)</label>
                <input
                  type="number"
                  value={form.behavior_patterns.session_duration_min}
                  onChange={(e) => setBehavior('session_duration_min', parseInt(e.target.value) || 0)}
                  className="w-full bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white"
                />
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Break Between Sessions (min)</label>
                <input
                  type="number"
                  value={form.behavior_patterns.break_between_sessions_min}
                  onChange={(e) => setBehavior('break_between_sessions_min', parseInt(e.target.value) || 0)}
                  className="w-full bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white"
                />
              </div>
            </div>
          </div>

          {/* Apps */}
          <div className="bg-card-alt border border-main rounded-xl p-6 space-y-4">
            <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Apps</h3>
            <div className="flex gap-2">
              <input
                value={appInput}
                onChange={(e) => setAppInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addApp())}
                className="flex-1 bg-zinc-900 border border-main rounded px-3 py-2 text-sm text-white"
                placeholder="com.instagram.android"
              />
              <button onClick={addApp} className="p-2 bg-zinc-800 border border-main rounded hover:bg-zinc-700">
                <Plus className="w-4 h-4" />
              </button>
            </div>
            {form.apps.map((app, i) => (
              <div key={i} className="flex items-center justify-between bg-zinc-900 border border-main rounded px-3 py-2">
                <span className="mono text-xs">{app.package}</span>
                <button onClick={() => removeApp(i)} className="text-zinc-500 hover:text-red-400">
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
