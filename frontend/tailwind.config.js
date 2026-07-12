/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        // Design tokens (plan 28) — mapped to the CSS custom properties in index.css so a
        // single token sheet drives dark + light. `<alpha-value>` keeps opacity utilities
        // (bg-card/50, border-border-main/40) working. Class names are unchanged from the
        // old hard-coded palette, so no view files needed editing for the tokenization.
        card: 'rgb(var(--bg-card) / <alpha-value>)',
        'card-alt': 'rgb(var(--bg-card-alt) / <alpha-value>)',
        'border-main': 'rgb(var(--border-main) / <alpha-value>)',
        'border-alt': 'rgb(var(--border-alt) / <alpha-value>)',
        body: 'rgb(var(--bg-body) / <alpha-value>)',
        hover: 'rgb(var(--bg-hover) / <alpha-value>)',
        // Semantic status tokens (emerald/amber/red/blue today; light may darken for contrast).
        ok: 'rgb(var(--ok) / <alpha-value>)',
        warn: 'rgb(var(--warn) / <alpha-value>)',
        err: 'rgb(var(--err) / <alpha-value>)',
        info: 'rgb(var(--info) / <alpha-value>)',
        // Runtime accent — driven by CSS custom properties set from the saved accent hex
        // (plan 12). `<alpha-value>` lets Tailwind opacity utilities (bg-accent/20) work.
        accent: 'rgb(var(--accent) / <alpha-value>)',
        'accent-hover': 'rgb(var(--accent-hover) / <alpha-value>)',
        'accent-dim': 'rgb(var(--accent-dim) / <alpha-value>)',
        'accent-bg': 'rgb(var(--accent-bg) / <alpha-value>)',
      },
    },
  },
  plugins: [],
}
