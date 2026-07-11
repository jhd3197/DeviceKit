import React from 'react'
import { AlertTriangle } from 'lucide-react'

// Per-extension error boundary (plan 04, ServerKit's "fail soft, loudly"). A broken
// extension component must never white-screen the app: it renders a contained failure card
// and logs loudly to the console so authors notice. One boundary wraps each contributed
// route and each contributed widget so a single bad extension can't take down its
// neighbours or the host.
export default class ExtensionErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Loud, attributable log so the author knows which extension failed.
    // eslint-disable-next-line no-console
    console.error(`[extension:${this.props.slug || 'unknown'}] render failed:`, error, info)
  }

  render() {
    if (this.state.error) {
      const compact = this.props.compact
      return (
        <div
          className={`bg-red-950/40 border border-red-900/50 rounded-lg text-red-300 ${
            compact ? 'p-3' : 'p-4 m-4'
          }`}
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span className="text-xs font-semibold">
              Extension “{this.props.slug || 'unknown'}” failed to render
            </span>
          </div>
          {!compact && (
            <p className="mt-1.5 text-[11px] text-red-400/80 mono break-all">
              {String(this.state.error?.message || this.state.error)}
            </p>
          )}
        </div>
      )
    }
    return this.props.children
  }
}
