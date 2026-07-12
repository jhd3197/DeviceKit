// Appearance pane (plan 12, extended plan 28): theme mode + accent color, both with a
// live-recoloring, no-reload apply.
//
// Theme mode (dark/light/system) writes <html data-theme> via setThemeMode() + localStorage
// and mirrors to `appearance.theme`. Accent calls setAccent() (writes the CSS ramp +
// localStorage) and mirrors to `appearance.accent`. For both, the server value is
// authoritative across browsers, so on load we reconcile localStorage to whatever settings
// carries — exactly the plan-12 pattern.
import React, { useEffect, useRef, useState } from 'react'
import { Check, Palette, Moon, Sun, Monitor, Upload, RotateCcw, Building2 } from 'lucide-react'
import { Pane, Field } from './fields'
import {
  ACCENT_PRESETS,
  DEFAULT_ACCENT,
  normalizeHex,
  setAccent,
  getStoredAccent,
  THEME_MODES,
  setThemeMode,
  getStoredThemeMode,
  subscribeTheme,
} from '../../theme'
import { useBrand, setBrand, brandName, DEFAULT_BRAND_NAME } from '../../brand'
import { useAuth } from '../../auth/AuthContext'
import Logo from '../Logo'

// A logo is stored inline as a data-URI. Downscale to <=256px and re-encode to PNG before
// saving so the settings row stays small (the backend also hard-caps the string length).
const LOGO_MAX_DIM = 256
function fileToLogoDataUri(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Could not read the file'))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error('That file is not a valid image'))
      img.onload = () => {
        const scale = Math.min(1, LOGO_MAX_DIM / Math.max(img.width, img.height))
        const w = Math.round(img.width * scale)
        const h = Math.round(img.height * scale)
        const canvas = document.createElement('canvas')
        canvas.width = w
        canvas.height = h
        canvas.getContext('2d').drawImage(img, 0, 0, w, h)
        resolve(canvas.toDataURL('image/png'))
      }
      img.src = reader.result
    }
    reader.readAsDataURL(file)
  })
}

// Mini-preview palettes for the mode picker — literal hexes (not tokens) so each swatch
// shows its own look regardless of the currently-active theme. Mirror index.css.
const MODE_META = {
  dark: { label: 'Dark', icon: Moon, body: '#000000', side: '#0a0a0a', card: '#0a0a0a', border: '#1a1a1a' },
  light: { label: 'Light', icon: Sun, body: '#f6f7fb', side: '#f1f3f9', card: '#ffffff', border: '#e2e6ef' },
}

function ModePreview({ mode }) {
  // System shows a diagonal light/dark split; dark/light show their own palette.
  const isSystem = mode === 'system'
  const d = MODE_META.dark
  const l = MODE_META.light
  const p = isSystem ? d : MODE_META[mode]
  return (
    <div
      className="relative h-14 w-full rounded-md overflow-hidden border flex"
      style={{ borderColor: p.border, background: p.body }}
    >
      {isSystem && (
        <div
          className="absolute inset-0"
          style={{ background: `linear-gradient(135deg, ${d.body} 0 50%, ${l.body} 50% 100%)` }}
        />
      )}
      <div className="relative w-1/4 h-full" style={{ background: isSystem ? d.side : p.side }} />
      <div className="relative flex-1 p-1.5 flex flex-col gap-1">
        <div className="h-2 rounded-sm" style={{ background: isSystem ? l.card : p.card, border: `1px solid ${isSystem ? l.border : p.border}` }} />
        <div className="h-2 w-2/3 rounded-sm" style={{ background: isSystem ? l.card : p.card, border: `1px solid ${isSystem ? l.border : p.border}` }} />
      </div>
    </div>
  )
}

export default function Appearance({ settings, save, register }) {
  const reg = register || (() => ({}))
  const serverAccent = normalizeHex(settings?.['appearance.accent']) || null
  const serverTheme = THEME_MODES.includes(settings?.['appearance.theme'])
    ? settings['appearance.theme']
    : null
  const [accent, setLocal] = useState(() => serverAccent || getStoredAccent())
  const [hexInput, setHexInput] = useState(accent)
  const [mode, setMode] = useState(() => getStoredThemeMode())

  // White-label (admin-only card). Brand name + logo reconcile from the server like accent.
  const { isAdmin } = useAuth()
  const brand = useBrand()
  const serverBrandName = typeof settings?.['appearance.brand_name'] === 'string'
    ? settings['appearance.brand_name'] : null
  const serverLogo = typeof settings?.['appearance.logo'] === 'string'
    ? settings['appearance.logo'] : null
  const [nameDraft, setNameDraft] = useState(brand.brandName)
  const [logoError, setLogoError] = useState(null)
  const fileRef = useRef(null)

  // Keep the picker in sync with mode changes from elsewhere (palette toggle, OS shift).
  useEffect(() => subscribeTheme(setMode), [])

  // Reconcile the server's saved brand over localStorage on load (authoritative cross-browser).
  useEffect(() => {
    if (serverBrandName === null && serverLogo === null) return
    const stored = brand
    const next = {}
    if (serverBrandName !== null && serverBrandName !== stored.brandName) next.brandName = serverBrandName
    if (serverLogo !== null && serverLogo !== stored.logo) next.logo = serverLogo
    if (Object.keys(next).length) {
      setBrand(next)
      if (next.brandName !== undefined) setNameDraft(next.brandName)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverBrandName, serverLogo])

  // Reconcile to the server's saved accent on load (authoritative across browsers).
  useEffect(() => {
    if (serverAccent && serverAccent !== getStoredAccent()) {
      setAccent(serverAccent)
      setLocal(serverAccent)
      setHexInput(serverAccent)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverAccent])

  // Reconcile to the server's saved theme mode on load (authoritative across browsers).
  useEffect(() => {
    if (serverTheme && serverTheme !== getStoredThemeMode()) {
      setThemeMode(serverTheme)
      setMode(serverTheme)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverTheme])

  const chooseMode = (m) => {
    setThemeMode(m)
    setMode(m)
    save({ 'appearance.theme': m }).catch(() => {})
  }

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

  // --- White-label handlers (admin) ---
  const saveBrandName = () => {
    const trimmed = nameDraft.trim()
    if (trimmed === brand.brandName) return
    setBrand({ brandName: trimmed })
    save({ 'appearance.brand_name': trimmed }).catch(() => {})
  }

  const onLogoPick = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-picking the same file
    if (!file) return
    setLogoError(null)
    try {
      const dataUri = await fileToLogoDataUri(file)
      setBrand({ logo: dataUri })
      const r = await save({ 'appearance.logo': dataUri })
      // Backend rejects an oversized logo with a 400; save() throws → caught below.
      if (r && r['appearance.logo'] !== undefined && r['appearance.logo'] !== dataUri) {
        setBrand({ logo: r['appearance.logo'] || '' })
      }
    } catch (err) {
      setLogoError(err.message || 'Could not save the logo')
      setBrand({ logo: serverLogo || '' }) // revert the optimistic apply
    }
  }

  const clearLogo = () => {
    setLogoError(null)
    setBrand({ logo: '' })
    save({ 'appearance.logo': '' }).catch(() => {})
  }

  const resetBrand = () => {
    setLogoError(null)
    setNameDraft('')
    setBrand({ brandName: '', logo: '' })
    save({ 'appearance.brand_name': '', 'appearance.logo': '' }).catch(() => {})
  }

  return (
    <Pane title="Appearance" description="Choose a theme mode and the accent color used across DeviceKit.">
      {/* Theme mode (plan 28) */}
      <Field
        label="Theme"
        help="Dark, Light, or follow your operating system. Applies instantly and syncs across your browsers."
        register={reg('theme-mode')}
      >
        <div className="grid grid-cols-3 gap-3 max-w-md">
          {THEME_MODES.map((m) => {
            const meta = m === 'system'
              ? { label: 'System', icon: Monitor }
              : MODE_META[m]
            const Icon = meta.icon
            const active = mode === m
            return (
              <button
                key={m}
                type="button"
                onClick={() => chooseMode(m)}
                className={`rounded-lg border p-2 text-left transition-colors ${
                  active ? 'border-accent bg-accent/5' : 'border-main hover:border-alt'
                }`}
              >
                <ModePreview mode={m} />
                <div className="flex items-center gap-1.5 mt-2 px-0.5">
                  <Icon className={`w-3.5 h-3.5 ${active ? 'text-accent' : 'text-zinc-400'}`} />
                  <span className={`text-xs font-medium ${active ? 'text-strong' : 'text-zinc-400'}`}>
                    {meta.label}
                  </span>
                  {active && <Check className="w-3.5 h-3.5 text-accent ml-auto" />}
                </div>
              </button>
            )
          })}
        </div>
      </Field>

      <Field
        label="Accent color"
        help="Recolors buttons, links, active states, and charts."
        register={reg('accent-color')}
      >
        <div className="flex items-center gap-2">
          {/* Native color picker — click the swatch to open the OS eyedropper/wheel. */}
          <input
            type="color"
            value={accent}
            onChange={(e) => choose(e.target.value)}
            title="Pick a custom color"
            className="w-8 h-8 rounded-md border border-alt shrink-0 bg-transparent cursor-pointer p-0"
            style={{ backgroundColor: accent }}
          />
          <input
            type="text"
            value={hexInput}
            onChange={(e) => setHexInput(e.target.value)}
            onBlur={onHexSubmit}
            onKeyDown={(e) => e.key === 'Enter' && onHexSubmit()}
            className="w-28 bg-body border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 font-mono focus:outline-none focus:border-accent"
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
                active ? 'border-strong' : 'border-transparent'
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
          className="h-9 px-3 rounded-md border border-alt text-xs text-zinc-400 hover:text-strong"
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
        Theme mode and accent are applied as CSS variables for an instant, no-reload recolor,
        and saved to this instance so your choice follows you across browsers.
      </div>

      {/* White-label (plan 28) — admin only. Renames the instance and swaps the mark shown
          on the sidebar, login screen, and browser tab title. */}
      {isAdmin && (
        <Field
          label="White-label"
          help="Rename this instance and replace the logo shown in the sidebar, on the login screen, and in the browser tab."
          register={reg('white-label')}
        >
          <div className="rounded-lg border border-main bg-card p-5 space-y-5">
            {/* Live brand preview */}
            <div className="flex items-center gap-3">
              <Logo size={36} className="rounded shrink-0" />
              <span className="font-bold tracking-tight text-lg text-strong">
                {nameDraft.trim() || brandName(brand)}
              </span>
              <span className="ml-auto text-[10px] text-zinc-500 uppercase tracking-widest flex items-center gap-1">
                <Building2 className="w-3.5 h-3.5" /> Brand
              </span>
            </div>

            {/* Brand name */}
            <div className="space-y-1.5">
              <label className="text-xs text-zinc-400">Brand name</label>
              <input
                type="text"
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onBlur={saveBrandName}
                onKeyDown={(e) => e.key === 'Enter' && saveBrandName()}
                placeholder={DEFAULT_BRAND_NAME}
                className="w-full max-w-xs bg-body border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-accent"
              />
            </div>

            {/* Logo */}
            <div className="space-y-1.5">
              <label className="text-xs text-zinc-400">Logo</label>
              <div className="flex items-center gap-2">
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/png,image/jpeg,image/svg+xml,image/webp"
                  onChange={onLogoPick}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  className="flex items-center gap-2 h-9 px-3 rounded-md border border-alt text-xs text-zinc-300 hover:text-strong hover:border-accent transition-colors"
                >
                  <Upload className="w-3.5 h-3.5" /> Upload image
                </button>
                {brand.logo && (
                  <button
                    type="button"
                    onClick={clearLogo}
                    className="h-9 px-3 rounded-md border border-alt text-xs text-zinc-400 hover:text-strong"
                  >
                    Remove
                  </button>
                )}
              </div>
              <p className="text-[11px] text-zinc-500">
                PNG/JPG/SVG/WebP, downscaled to 256px and stored on this instance (max ~380 KB).
              </p>
              {logoError && <p className="text-[11px] text-err">{logoError}</p>}
            </div>

            <button
              type="button"
              onClick={resetBrand}
              className="flex items-center gap-2 text-xs text-zinc-400 hover:text-strong"
            >
              <RotateCcw className="w-3.5 h-3.5" /> Reset to DeviceKit branding
            </button>
          </div>
        </Field>
      )}
    </Pane>
  )
}
