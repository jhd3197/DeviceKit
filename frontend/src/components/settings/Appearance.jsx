// Appearance pane (plan 12): accent color picker with a live-recoloring ramp.
//
// Changing the accent calls setAccent() (writes the CSS ramp + localStorage) for an instant,
// no-reload recolor, and persists `appearance.accent` to the settings row so the choice
// survives a fresh browser. The server value is authoritative across devices, so on load we
// reconcile localStorage to whatever settings carries.
import React, { useEffect, useState } from 'react'
import { Check, Palette } from 'lucide-react'
import { Pane, Field } from './fields'
import {
  ACCENT_PRESETS,
  DEFAULT_ACCENT,
  normalizeHex,
  setAccent,
  getStoredAccent,
} from '../../theme'

export default function Appearance({ settings, save }) {
  const serverAccent = normalizeHex(settings?.['appearance.accent']) || null
  const [accent, setLocal] = useState(() => serverAccent || getStoredAccent())
  const [hexInput, setHexInput] = useState(accent)

  // Reconcile to the server's saved accent on load (authoritative across browsers).
  useEffect(() => {
    if (serverAccent && serverAccent !== getStoredAccent()) {
      setAccent(serverAccent)
      setLocal(serverAccent)
      setHexInput(serverAccent)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverAccent])

  const choose = (hex) => {
    const clean = setAccent(hex) // apply + persist locally, returns normalized
    setLocal(clean)
    setHexInput(clean)
    save({ 'appearance.accent': clean }).catch(() => {})
  }

  const onHexSubmit = () => {
    const clean = normalizeHex(hexInput)
    if (clean) choose(clean)
    else setHexInput(accent) // revert invalid input
  }

  return (
    <Pane title="Appearance" description="Personalize the accent color used across DeviceKit.">
      <Field label="Accent color" help="Recolors buttons, links, active states, and charts.">
        <div className="flex items-center gap-2">
          <span
            className="w-8 h-8 rounded-md border border-alt shrink-0"
            style={{ backgroundColor: accent }}
          />
          <input
            type="text"
            value={hexInput}
            onChange={(e) => setHexInput(e.target.value)}
            onBlur={onHexSubmit}
            onKeyDown={(e) => e.key === 'Enter' && onHexSubmit()}
            className="w-28 bg-black border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 font-mono focus:outline-none focus:border-accent"
          />
        </div>
      </Field>

      {/* Presets */}
      <div className="flex flex-wrap gap-2">
        {ACCENT_PRESETS.map((p) => {
          const active = normalizeHex(p.hex) === accent
          return (
            <button
              key={p.hex}
              type="button"
              onClick={() => choose(p.hex)}
              title={p.name}
              className={`w-9 h-9 rounded-md flex items-center justify-center border transition-transform hover:scale-105 ${
                active ? 'border-white' : 'border-transparent'
              }`}
              style={{ backgroundColor: p.hex }}
            >
              {active && <Check className="w-4 h-4 text-white drop-shadow" />}
            </button>
          )
        })}
        <button
          type="button"
          onClick={() => choose(DEFAULT_ACCENT)}
          className="h-9 px-3 rounded-md border border-alt text-xs text-zinc-400 hover:text-white"
        >
          Reset
        </button>
      </div>

      {/* Live preview */}
      <div className="rounded-lg border border-main bg-card p-5 space-y-4">
        <div className="flex items-center gap-2 text-xs text-zinc-500 uppercase tracking-widest">
          <Palette className="w-3.5 h-3.5" /> Preview
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button className="bg-accent hover:bg-accent-hover text-black text-sm font-semibold px-4 py-2 rounded-md transition-colors">
            Primary action
          </button>
          <span className="text-accent text-sm font-medium">Accented link</span>
          <span className="text-xs px-2 py-1 rounded-full bg-accent/10 text-accent border border-accent/20">
            Active
          </span>
          <span className="w-24 h-2 rounded-full bg-accent" />
        </div>
      </div>

      <div className="rounded-md border border-main bg-card p-4 text-xs text-zinc-500 leading-relaxed">
        DeviceKit currently ships a single dark theme. The accent ramp is derived from your
        color and applied as CSS variables, so light mode and white-labeling can build on the
        same mechanism later.
      </div>
    </Pane>
  )
}
