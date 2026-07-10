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
        card: '#0a0a0a',
        'card-alt': '#050505',
        'border-main': '#1a1a1a',
        'border-alt': '#2e2e2e',
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
