import React, { useEffect, useRef } from 'react'
import { Eye, EyeOff, ChevronUp, ChevronDown, RotateCcw, X } from 'lucide-react'

// "Customize layout" popover for the dashboard (plan 11). Lists every widget in order with
// a show/hide toggle and up/down controls — ServerKit's exact ordered-list interaction, no
// drag-drop dependency. Changes persist immediately via the layout hook's setters.
export default function DashboardLayoutEditor({ widgets, toggleWidget, moveWidget, resetLayout, onClose }) {
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose()
    }
    const esc = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', handler)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', handler)
      document.removeEventListener('keydown', esc)
    }
  }, [onClose])

  return (
    <div
      ref={ref}
      className="absolute top-full right-0 mt-2 w-72 bg-zinc-900 border border-main rounded-lg shadow-xl z-30"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-main">
        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
          Customize Layout
        </span>
        <button onClick={onClose} className="text-zinc-500 hover:text-white transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="py-1">
        {widgets.map((w, i) => (
          <div
            key={w.id}
            className="flex items-center gap-2 px-3 py-1.5 hover:bg-zinc-800/50 group"
          >
            <button
              onClick={() => toggleWidget(w.id)}
              className={`transition-colors ${w.visible ? 'text-emerald-500 hover:text-emerald-400' : 'text-zinc-600 hover:text-zinc-400'}`}
              title={w.visible ? 'Hide widget' : 'Show widget'}
            >
              {w.visible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
            </button>
            <span className={`flex-1 text-xs ${w.visible ? 'text-zinc-200' : 'text-zinc-500'}`}>
              {w.label}
            </span>
            <button
              onClick={() => moveWidget(w.id, 'up')}
              disabled={i === 0}
              className="text-zinc-500 hover:text-white disabled:opacity-20 disabled:hover:text-zinc-500 transition-colors"
              title="Move up"
            >
              <ChevronUp className="w-4 h-4" />
            </button>
            <button
              onClick={() => moveWidget(w.id, 'down')}
              disabled={i === widgets.length - 1}
              className="text-zinc-500 hover:text-white disabled:opacity-20 disabled:hover:text-zinc-500 transition-colors"
              title="Move down"
            >
              <ChevronDown className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="px-3 py-2 border-t border-main">
        <button
          onClick={resetLayout}
          className="flex items-center gap-1.5 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <RotateCcw className="w-3 h-3" /> Reset to default
        </button>
      </div>
    </div>
  )
}
