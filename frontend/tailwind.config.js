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
      },
    },
  },
  plugins: [],
}
