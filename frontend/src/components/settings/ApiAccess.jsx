// API Access pane (plan 12): view/set the X-API-Key the frontend sends.
//
// DeviceKit's server-side auth is the `API_KEY` env var (empty = auth disabled in dev). The
// frontend attaches whatever key is stored in localStorage (`devicekit_api_key`) as the
// `X-API-Key` header (see api.js). This pane surfaces and edits that local key — the piece a
// user actually controls from the browser — with show/hide + copy. Scoped/rotatable keys are
// a future server feature; noted here so the pane has a home for them.
import React, { useState } from 'react'
import { Eye, EyeOff, Copy, Check, KeyRound } from 'lucide-react'
import { Pane, Field, SaveBar } from './fields'

const LS_KEY = 'devicekit_api_key'

export default function ApiAccess() {
  const [value, setValue] = useState(() => localStorage.getItem(LS_KEY) || '')
  const [baseline, setBaseline] = useState(value)
  const [show, setShow] = useState(false)
  const [copied, setCopied] = useState(false)
  const [savedAt, setSavedAt] = useState(null)

  const dirty = value !== baseline

  const save = () => {
    if (value) localStorage.setItem(LS_KEY, value)
    else localStorage.removeItem(LS_KEY)
    setBaseline(value)
    setSavedAt(Date.now())
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <Pane
      title="API Access"
      description="The X-API-Key this browser sends with every request. It must match the backend's API_KEY env var (empty = auth disabled in dev)."
    >
      <Field
        label="API key"
        help="Stored in this browser only. Reloads pick it up automatically."
        htmlFor="api-key"
      >
        <div className="flex items-center gap-2 w-full">
          <div className="relative flex-1">
            <KeyRound className="w-4 h-4 text-zinc-600 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              id="api-key"
              type={show ? 'text' : 'password'}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="No key set (dev mode)"
              className="w-full bg-black border border-alt rounded-md pl-9 pr-3 py-2 text-sm text-zinc-200 font-mono placeholder:text-zinc-600 focus:outline-none focus:border-accent"
            />
          </div>
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            title={show ? 'Hide' : 'Show'}
            className="p-2 text-zinc-400 hover:text-white border border-alt rounded-md"
          >
            {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
          <button
            type="button"
            onClick={copy}
            disabled={!value}
            title="Copy"
            className="p-2 text-zinc-400 hover:text-white border border-alt rounded-md disabled:opacity-40"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
          </button>
        </div>
      </Field>

      <div className="rounded-md border border-main bg-card p-4 text-xs text-zinc-500 leading-relaxed">
        Scoped, server-issued keys (per-agent, revocable) are a planned backend feature. Today
        a single shared key gates the API; set it in the backend <span className="font-mono text-zinc-400">.env</span>{' '}
        as <span className="font-mono text-zinc-400">API_KEY</span> and paste the same value here.
      </div>

      <SaveBar dirty={dirty} saving={false} savedAt={savedAt} onSave={save} onReset={() => setValue(baseline)} />
    </Pane>
  )
}
