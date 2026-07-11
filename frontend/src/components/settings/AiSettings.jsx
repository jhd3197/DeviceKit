// AI settings pane (plan 12): Prompture default model, per-feature overrides, provider keys.
//
// The default model + per-feature overrides go through the shared pane-form (persisted as
// `ai.default_model` / `ai.model_overrides`). Provider keys are handled separately: the
// backend redacts them to booleans on read, and the merge semantics clear a key on a blank
// value — so this pane only sends keys the user actually typed, and offers an explicit
// Clear per provider.
import React, { useState } from 'react'
import { Sparkles, Check } from 'lucide-react'
import { Pane, Field, TextInput, SaveBar } from './fields'
import { usePaneForm } from './usePaneForm'
import { api } from '../../api'

const KEYS = ['ai.default_model', 'ai.model_overrides']

// Model id used across every AI feature unless overridden below.
const FEATURES = [
  { key: 'generation', label: 'Automation generation', help: 'NL → automation steps.' },
  { key: 'self_heal', label: 'Self-heal', help: 'Repairing a failed step mid-run.' },
  { key: 'analysis', label: 'Failure analysis', help: 'Explaining debug bundles.' },
]

// Known providers → the env var Prompture reads. Presence shown from the redacted booleans.
const PROVIDERS = [
  { name: 'Anthropic', env: 'ANTHROPIC_API_KEY' },
  { name: 'OpenAI', env: 'OPENAI_API_KEY' },
  { name: 'Google (Gemini)', env: 'GEMINI_API_KEY' },
]

function ProviderKeys({ settings, save }) {
  const present = settings?.['ai.provider_keys'] || {}
  const [drafts, setDrafts] = useState({}) // env -> typed value
  const [saving, setSaving] = useState(null)
  const [savedEnv, setSavedEnv] = useState(null)

  const commit = async (env, value) => {
    setSaving(env)
    try {
      await save({ 'ai.provider_keys': { [env]: value } })
      setDrafts((d) => ({ ...d, [env]: '' }))
      setSavedEnv(env)
      setTimeout(() => setSavedEnv((e) => (e === env ? null : e)), 1500)
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-zinc-200">Provider keys</h3>
        <p className="text-xs text-zinc-500 mt-0.5">
          Stored server-side and applied to the environment immediately — no <span className="font-mono">.env</span> edit
          or restart. Keys are never shown back.
        </p>
      </div>
      {PROVIDERS.map((p) => (
        <div key={p.env} className="flex items-center gap-2">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm text-zinc-200">{p.name}</span>
              {present[p.env] ? (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  set
                </span>
              ) : (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">not set</span>
              )}
              <span className="text-[10px] font-mono text-zinc-600">{p.env}</span>
            </div>
            <input
              type="password"
              value={drafts[p.env] || ''}
              onChange={(e) => setDrafts((d) => ({ ...d, [p.env]: e.target.value }))}
              placeholder={present[p.env] ? '•••••••• (leave blank to keep)' : 'Paste API key'}
              className="mt-1 w-full bg-black border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 font-mono placeholder:text-zinc-600 focus:outline-none focus:border-accent"
            />
          </div>
          <div className="flex flex-col gap-1 pt-6">
            <button
              type="button"
              disabled={!drafts[p.env] || saving === p.env}
              onClick={() => commit(p.env, drafts[p.env])}
              className="text-xs bg-white text-black font-semibold px-3 py-1.5 rounded-md disabled:opacity-40"
            >
              {savedEnv === p.env ? <Check className="w-3.5 h-3.5" /> : 'Save'}
            </button>
            {present[p.env] && (
              <button
                type="button"
                onClick={() => commit(p.env, '')}
                className="text-xs text-red-400 hover:text-red-300 px-3"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function AiSettings({ settings, save }) {
  const f = usePaneForm(settings, KEYS, save)
  const overrides = f.draft['ai.model_overrides'] || {}
  const setOverride = (feature, value) =>
    f.set('ai.model_overrides', { ...overrides, [feature]: value })

  return (
    <Pane
      title="AI"
      description="Prompture model configuration. These replace what used to live only in .env."
    >
      <Field
        label="Default model"
        help="e.g. claude/claude-sonnet-4-20250514. Blank uses the server's PROMPTURE_DEFAULT_MODEL."
        htmlFor="ai-default-model"
      >
        <TextInput
          id="ai-default-model"
          value={f.draft['ai.default_model']}
          onChange={(v) => f.set('ai.default_model', v || null)}
          placeholder="claude/claude-sonnet-4-20250514"
        />
      </Field>

      <div className="pt-2">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-4 h-4 text-accent" />
          <h3 className="text-sm font-semibold text-zinc-200">Per-feature overrides</h3>
        </div>
        <div className="space-y-4">
          {FEATURES.map((feat) => (
            <Field key={feat.key} label={feat.label} help={feat.help} htmlFor={`ov-${feat.key}`}>
              <TextInput
                id={`ov-${feat.key}`}
                value={overrides[feat.key]}
                onChange={(v) => setOverride(feat.key, v || undefined)}
                placeholder="use default"
              />
            </Field>
          ))}
        </div>
      </div>

      {f.error && <p className="text-xs text-red-400">{f.error}</p>}
      <SaveBar dirty={f.dirty} saving={f.saving} savedAt={f.savedAt} onSave={f.persist} onReset={f.reset} />

      <div className="pt-6 border-t border-main">
        <ProviderKeys settings={settings} save={save} />
      </div>
    </Pane>
  )
}
