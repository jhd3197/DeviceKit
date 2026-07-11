// AI settings pane (plan 12 + plan 19): Prompture model configuration, backend selection
// (direct provider keys vs a prompture-hub gateway), provider/hub secrets.
//
// The default model + per-feature overrides go through the shared pane-form (persisted as
// `ai.default_model` / `ai.model_overrides`, plus `ai.backend` / `ai.hub.url`). Secrets are
// handled separately: the backend redacts them on read (booleans), and blank clears — so
// this pane only sends secrets the user actually typed.
//
// On the hub backend the pane probes `GET /ai/hub/health` (a server-side proxy — the hub
// URL never needs to be browser-reachable) and, when the hub answers, feeds its key-scoped
// `/v1/models` list into the model pickers so users choose from what their key allows.
import React, { useCallback, useEffect, useState } from 'react'
import { Sparkles, Check, RefreshCw, ExternalLink } from 'lucide-react'
import { Pane, Field, TextInput, Select, SaveBar } from './fields'
import { usePaneForm } from './usePaneForm'
import { api } from '../../api'

const KEYS = ['ai.default_model', 'ai.model_overrides', 'ai.backend', 'ai.hub.url']

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

// Free-text model input that upgrades to a picker when the hub reports what this key may use.
function ModelInput({ id, value, onChange, placeholder, hubModels }) {
  if (hubModels && hubModels.length > 0) {
    return (
      <Select
        id={id}
        value={value ?? ''}
        onChange={(v) => onChange(v || null)}
        options={[{ value: '', label: placeholder }, ...hubModels.map((m) => ({ value: m, label: m }))]}
      />
    )
  }
  return <TextInput id={id} value={value} onChange={(v) => onChange(v || null)} placeholder={placeholder} />
}

function SecretInput({ label, envHint, present, placeholder, onSave, onClear }) {
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const commit = async (value) => {
    setSaving(true)
    try {
      await onSave(value)
      setDraft('')
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm text-zinc-200">{label}</span>
          {present ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              set
            </span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">not set</span>
          )}
          {envHint && <span className="text-[10px] font-mono text-zinc-600">{envHint}</span>}
        </div>
        <input
          type="password"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={present ? '•••••••• (leave blank to keep)' : placeholder}
          className="mt-1 w-full bg-black border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 font-mono placeholder:text-zinc-600 focus:outline-none focus:border-accent"
        />
      </div>
      <div className="flex flex-col gap-1 pt-6">
        <button
          type="button"
          disabled={!draft || saving}
          onClick={() => commit(draft)}
          className="text-xs bg-white text-black font-semibold px-3 py-1.5 rounded-md disabled:opacity-40"
        >
          {saved ? <Check className="w-3.5 h-3.5" /> : 'Save'}
        </button>
        {present && onClear && (
          <button type="button" onClick={() => commit('')} className="text-xs text-red-400 hover:text-red-300 px-3">
            Clear
          </button>
        )}
      </div>
    </div>
  )
}

function ProviderKeys({ settings, save }) {
  const present = settings?.['ai.provider_keys'] || {}
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
        <SecretInput
          key={p.env}
          label={p.name}
          envHint={p.env}
          present={!!present[p.env]}
          placeholder="Paste API key"
          onSave={(value) => save({ 'ai.provider_keys': { [p.env]: value } })}
          onClear
        />
      ))}
    </div>
  )
}

// Health probe + setup help for the hub backend (phase-10 Test-Connection pattern).
function HubStatus({ health, probing, onProbe }) {
  const url = health?.url || 'http://localhost:1984'
  return (
    <div className="rounded-md border border-alt bg-zinc-900/60 p-3 space-y-2">
      <div className="flex items-center gap-2">
        {probing ? (
          <span className="w-2 h-2 rounded-full bg-zinc-500 animate-pulse" />
        ) : (
          <span className={`w-2 h-2 rounded-full ${health?.reachable ? 'bg-emerald-400' : 'bg-red-400'}`} />
        )}
        <span className="text-sm text-zinc-200">
          {probing
            ? 'Probing hub…'
            : health?.reachable
              ? `Hub reachable${health.models?.length ? ` · ${health.models.length} model${health.models.length === 1 ? '' : 's'} allowed` : ''}`
              : `Hub not reachable at ${url}`}
        </span>
        <button
          type="button"
          onClick={onProbe}
          disabled={probing}
          className="ml-auto text-xs text-zinc-400 hover:text-white flex items-center gap-1 disabled:opacity-40"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${probing ? 'animate-spin' : ''}`} />
          Test
        </button>
      </div>
      {health?.reachable && health?.models_error && (
        <p className="text-xs text-amber-400">{health.models_error}</p>
      )}
      {health?.reachable && (
        <a
          href={`${url}/app/`}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-blue-400 hover:text-blue-300 inline-flex items-center gap-1"
        >
          Open hub dashboard <ExternalLink className="w-3 h-3" />
        </a>
      )}
      {!probing && health && !health.reachable && (
        <div className="text-xs text-zinc-500 space-y-1 pt-1">
          <p>
            Install and start the hub:{' '}
            <span className="font-mono text-zinc-300">pip install prompture-hub</span> then{' '}
            <span className="font-mono text-zinc-300">prompture-hub</span>. Run it natively (not in
            Docker) so it can reach localhost model servers like Ollama.
          </p>
          <p>
            Then open <span className="font-mono text-zinc-300">{url}/app/</span>, create an API key
            (<span className="font-mono">ph_…</span>), and paste it below.
          </p>
        </div>
      )}
    </div>
  )
}

export default function AiSettings({ settings, save }) {
  const f = usePaneForm(settings, KEYS, save)
  const overrides = f.draft['ai.model_overrides'] || {}
  const setOverride = (feature, value) =>
    f.set('ai.model_overrides', { ...overrides, [feature]: value })

  const backend = f.draft['ai.backend'] || 'direct'
  const hubKeySet = !!settings?.['ai.hub.key']

  const [health, setHealth] = useState(null)
  const [probing, setProbing] = useState(false)

  const probe = useCallback(async () => {
    setProbing(true)
    try {
      setHealth(await api.getAiHubHealth())
    } catch {
      setHealth({ reachable: false })
    } finally {
      setProbing(false)
    }
  }, [])

  // Probe automatically whenever the hub backend is selected (or its config was saved).
  useEffect(() => {
    if (backend === 'hub') probe()
  }, [backend, settings?.['ai.hub.url'], hubKeySet, probe])

  const hubModels = backend === 'hub' && settings?.['ai.backend'] === 'hub' ? health?.models : null

  return (
    <Pane
      title="AI"
      description="Prompture model configuration. These replace what used to live only in .env."
    >
      <Field
        label="Backend"
        help="Direct uses provider keys stored here. Prompture Hub routes every AI call through a self-hosted gateway holding the real keys — DeviceKit only stores one scoped hub key."
        htmlFor="ai-backend"
      >
        <Select
          id="ai-backend"
          value={backend}
          onChange={(v) => f.set('ai.backend', v)}
          options={[
            { value: 'direct', label: 'Direct (provider keys)' },
            { value: 'hub', label: 'Prompture Hub' },
          ]}
        />
      </Field>

      {backend === 'hub' && (
        <>
          <Field
            label="Hub URL"
            help="Where prompture-hub is running. The backend probes it server-side."
            htmlFor="ai-hub-url"
          >
            <TextInput
              id="ai-hub-url"
              value={f.draft['ai.hub.url']}
              onChange={(v) => f.set('ai.hub.url', v || null)}
              placeholder="http://localhost:1984"
            />
          </Field>
          <HubStatus health={health} probing={probing} onProbe={probe} />
          <SecretInput
            label="Hub key"
            envHint="ph_…"
            present={hubKeySet}
            placeholder="Paste hub key (ph_…)"
            onSave={(value) => save({ 'ai.hub.key': value })}
            onClear
          />
        </>
      )}

      <Field
        label="Default model"
        help={
          hubModels?.length
            ? 'Models your hub key is allowed to use.'
            : "e.g. claude/claude-sonnet-4-20250514. Blank uses the server's PROMPTURE_DEFAULT_MODEL."
        }
        htmlFor="ai-default-model"
      >
        <ModelInput
          id="ai-default-model"
          value={f.draft['ai.default_model']}
          onChange={(v) => f.set('ai.default_model', v)}
          placeholder="claude/claude-sonnet-4-20250514"
          hubModels={hubModels}
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
              <ModelInput
                id={`ov-${feat.key}`}
                value={overrides[feat.key]}
                onChange={(v) => setOverride(feat.key, v || undefined)}
                placeholder="use default"
                hubModels={hubModels}
              />
            </Field>
          ))}
        </div>
      </div>

      {f.error && <p className="text-xs text-red-400">{f.error}</p>}
      <SaveBar dirty={f.dirty} saving={f.saving} savedAt={f.savedAt} onSave={f.persist} onReset={f.reset} />

      {backend === 'direct' && (
        <div className="pt-6 border-t border-main">
          <ProviderKeys settings={settings} save={save} />
        </div>
      )}
    </Pane>
  )
}
