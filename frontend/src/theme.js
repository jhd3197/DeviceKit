// Runtime accent theming (plan 12, ported from ServerKit's ThemeContext accent ramp).
//
// From one accent hex we derive a small ramp — base / hover (brighter) / dim (darker) /
// bg (very dark tint) — and write each as an "R G B" CSS custom property on
// <documentElement>. Tailwind maps `accent`/`accent-hover`/… to those vars via
// rgb(var(--accent) / <alpha-value>), so setting the properties recolors every accent
// utility instantly with no re-render. The chosen hex is mirrored to localStorage so the
// accent is correct on the very first paint after reload (before settings load over HTTP).

export const DEFAULT_ACCENT = '#6d7cff' // periwinkle — DeviceKit's brand purple (plan 27)
const LS_KEY = 'devicekit_accent'

// A few presets for the picker; users can also enter any hex. Periwinkle (the brand default)
// and Indigo lead — the same two-purples split the logo uses (#6d7cff live / #6366f1 deep).
// Emerald stays available for users who prefer the historical accent; semantic emerald
// (online/pass/success) is unaffected by this list — only brand chrome rides the accent ramp.
export const ACCENT_PRESETS = [
  { name: 'Periwinkle', hex: '#6d7cff' },
  { name: 'Indigo', hex: '#6366f1' },
  { name: 'Emerald', hex: '#10b981' },
  { name: 'Blue', hex: '#3b82f6' },
  { name: 'Violet', hex: '#8b5cf6' },
  { name: 'Amber', hex: '#f59e0b' },
  { name: 'Rose', hex: '#f43f5e' },
  { name: 'Cyan', hex: '#06b6d4' },
]

export function normalizeHex(hex) {
  if (typeof hex !== 'string') return null
  let h = hex.trim().replace(/^#/, '')
  if (h.length === 3) h = h.split('').map((c) => c + c).join('')
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null
  return `#${h.toLowerCase()}`
}

function hexToRgb(hex) {
  const h = normalizeHex(hex) || DEFAULT_ACCENT
  const n = parseInt(h.slice(1), 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

function rgbToHsl({ r, g, b }) {
  r /= 255
  g /= 255
  b /= 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  let h = 0
  let s = 0
  const l = (max + min) / 2
  const d = max - min
  if (d !== 0) {
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r:
        h = (g - b) / d + (g < b ? 6 : 0)
        break
      case g:
        h = (b - r) / d + 2
        break
      default:
        h = (r - g) / d + 4
    }
    h /= 6
  }
  return { h: h * 360, s: s * 100, l: l * 100 }
}

function hslToRgb({ h, s, l }) {
  h = ((h % 360) + 360) % 360
  s = Math.max(0, Math.min(100, s)) / 100
  l = Math.max(0, Math.min(100, l)) / 100
  const c = (1 - Math.abs(2 * l - 1)) * s
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = l - c / 2
  let r = 0
  let g = 0
  let b = 0
  if (h < 60) [r, g, b] = [c, x, 0]
  else if (h < 120) [r, g, b] = [x, c, 0]
  else if (h < 180) [r, g, b] = [0, c, x]
  else if (h < 240) [r, g, b] = [0, x, c]
  else if (h < 300) [r, g, b] = [x, 0, c]
  else [r, g, b] = [c, 0, x]
  return {
    r: Math.round((r + m) * 255),
    g: Math.round((g + m) * 255),
    b: Math.round((b + m) * 255),
  }
}

const triplet = ({ r, g, b }) => `${r} ${g} ${b}`

// Derive the four accent stops from one hex via HSL lightness shifts.
export function deriveRamp(hex) {
  const base = hexToRgb(hex)
  const hsl = rgbToHsl(base)
  return {
    accent: triplet(base),
    hover: triplet(hslToRgb({ ...hsl, l: Math.min(96, hsl.l + 12) })),
    dim: triplet(hslToRgb({ ...hsl, l: Math.max(4, hsl.l - 12) })),
    bg: triplet(hslToRgb({ ...hsl, s: Math.min(hsl.s, 60), l: Math.max(8, hsl.l - 38) })),
  }
}

// Write the ramp onto :root. Recolors every accent utility immediately.
export function applyAccent(hex) {
  const clean = normalizeHex(hex) || DEFAULT_ACCENT
  const ramp = deriveRamp(clean)
  const root = document.documentElement
  root.style.setProperty('--accent', ramp.accent)
  root.style.setProperty('--accent-hover', ramp.hover)
  root.style.setProperty('--accent-dim', ramp.dim)
  root.style.setProperty('--accent-bg', ramp.bg)
  return clean
}

export function getStoredAccent() {
  return normalizeHex(localStorage.getItem(LS_KEY)) || DEFAULT_ACCENT
}

// Persist + apply. Call on user change; storing first keeps reload paint correct.
export function setAccent(hex) {
  const clean = normalizeHex(hex) || DEFAULT_ACCENT
  localStorage.setItem(LS_KEY, clean)
  return applyAccent(clean)
}

// Apply the locally-stored accent as early as possible (before first paint of the app).
export function bootAccent() {
  applyAccent(getStoredAccent())
}
