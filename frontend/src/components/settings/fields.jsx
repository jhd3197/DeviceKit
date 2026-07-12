// Shared form primitives for the Settings panes (plan 12). Keeps every pane visually
// consistent — a labelled row with help text, wrapping inputs/selects/toggles/buttons in
// the DeviceKit dark theme.
import React from 'react'

// A labelled section container for one pane.
export function Pane({ title, description, children }) {
  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h2 className="text-lg font-bold tracking-tight">{title}</h2>
        {description && <p className="text-xs text-zinc-500 mt-1">{description}</p>}
      </div>
      <div className="space-y-6">{children}</div>
    </div>
  )
}

// A single labelled field row: label + optional help on the left, control on the right.
// `register` (optional) is a props object from useSettingFocus — spread it BEFORE className so
// the deep-link ref/data-setting-id land on the root div without clobbering styles.
export function Field({ label, help, htmlFor, children, register }) {
  return (
    <div {...register} className="grid grid-cols-[1fr_auto] gap-4 items-start">
      <div>
        <label htmlFor={htmlFor} className="text-sm font-medium text-zinc-200 block">
          {label}
        </label>
        {help && <p className="text-xs text-zinc-500 mt-0.5 max-w-sm">{help}</p>}
      </div>
      <div className="min-w-[14rem] flex justify-end">{children}</div>
    </div>
  )
}

export function TextInput({ id, value, onChange, placeholder, type = 'text', className = '' }) {
  return (
    <input
      id={id}
      type={type}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full bg-black border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-accent ${className}`}
    />
  )
}

export function NumberInput({ id, value, onChange, min, max, step = 1, suffix }) {
  return (
    <div className="flex items-center gap-2">
      <input
        id={id}
        type="number"
        value={value ?? ''}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        className="w-24 bg-black border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-accent"
      />
      {suffix && <span className="text-xs text-zinc-500">{suffix}</span>}
    </div>
  )
}

export function Select({ id, value, onChange, options }) {
  return (
    <select
      id={id}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-black border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-accent"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

// An accessible on/off toggle.
export function Toggle({ id, checked, onChange }) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        checked ? 'bg-accent' : 'bg-zinc-700'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  )
}

// A footer save bar shown when a pane has unsaved edits.
export function SaveBar({ dirty, saving, onSave, onReset, savedAt }) {
  return (
    <div className="flex items-center gap-3 pt-4 mt-2 border-t border-main">
      <button
        type="button"
        disabled={!dirty || saving}
        onClick={onSave}
        className="bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors"
      >
        {saving ? 'Saving…' : 'Save changes'}
      </button>
      {dirty && (
        <button
          type="button"
          onClick={onReset}
          className="text-sm text-zinc-400 hover:text-white px-2 py-2"
        >
          Discard
        </button>
      )}
      {!dirty && savedAt && <span className="text-xs text-emerald-400">Saved</span>}
    </div>
  )
}
