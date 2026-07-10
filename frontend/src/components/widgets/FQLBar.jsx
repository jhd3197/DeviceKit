import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Search, Play, Save, BookmarkPlus, Download, Zap, ChevronDown, Trash2 } from 'lucide-react'
import { api } from '../../api'

// Fleet-query bar: expression input with field autocomplete, preset + saved-query dropdowns,
// CSV export, and bulk actions over the matched set. Self-contained widget carved from
// Dashboard.jsx (plan 11) — it owns the query state and reports results up via `onResult`
// so the device-registry widget can render the matched set. An optional `initialQuery`
// (e.g. the command palette's `?q=`) runs once on mount.
export default function FQLBar({ initialQuery = '', onResult }) {
  const [queryExpr, setQueryExpr] = useState('')
  const [queryActive, setQueryActive] = useState(false)
  const [queryMatches, setQueryMatches] = useState(null)
  const [queryError, setQueryError] = useState(null)
  const [queryLoading, setQueryLoading] = useState(false)
  const [queryFields, setQueryFields] = useState({})
  const [presetQueries, setPresetQueries] = useState([])
  const [savedQueries, setSavedQueries] = useState([])
  const [showPresets, setShowPresets] = useState(false)
  const [showSaved, setShowSaved] = useState(false)
  const [showAutocomplete, setShowAutocomplete] = useState(false)
  const [showBulkAction, setShowBulkAction] = useState(false)
  const queryInputRef = useRef(null)
  const presetsRef = useRef(null)
  const savedRef = useRef(null)

  // Report result changes up to the composer so the registry widget can show matches.
  const report = useCallback((active, matches) => {
    onResult?.({ active, matches })
  }, [onResult])

  // Load query metadata on mount
  useEffect(() => {
    api.getQueryFields().then(r => setQueryFields(r.fields || {})).catch(() => {})
    api.getQueryPresets().then(r => setPresetQueries(r.presets || [])).catch(() => {})
    api.getSavedQueries().then(r => setSavedQueries(r.queries || [])).catch(() => {})
  }, [])

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e) => {
      if (presetsRef.current && !presetsRef.current.contains(e.target)) setShowPresets(false)
      if (savedRef.current && !savedRef.current.contains(e.target)) setShowSaved(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const executeQuery = async (expr) => {
    const q = (expr ?? queryExpr).trim()
    if (!q) {
      setQueryActive(false)
      setQueryMatches(null)
      setQueryError(null)
      report(false, null)
      return
    }
    setQueryLoading(true)
    setQueryError(null)
    try {
      const result = await api.fleetQuery(q)
      const matches = result.matches || []
      setQueryMatches(matches)
      setQueryActive(true)
      report(true, matches)
    } catch (e) {
      setQueryError(e.message || 'Query failed')
      setQueryMatches(null)
      report(false, null)
    } finally {
      setQueryLoading(false)
    }
  }

  const clearQuery = () => {
    setQueryExpr('')
    setQueryActive(false)
    setQueryMatches(null)
    setQueryError(null)
    report(false, null)
  }

  // Apply an FQL expression passed via `initialQuery` (e.g. "Open in Dashboard" from the
  // command palette). Runs once when a non-empty value is present.
  const appliedInitial = useRef(false)
  useEffect(() => {
    if (initialQuery && !appliedInitial.current) {
      appliedInitial.current = true
      setQueryExpr(initialQuery)
      executeQuery(initialQuery)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery])

  const saveCurrentQuery = async () => {
    const name = prompt('Save query as:')
    if (!name) return
    try {
      const q = await api.createSavedQuery({ name, expression: queryExpr })
      setSavedQueries(prev => [...prev, q])
    } catch {}
  }

  const deleteSavedQuery = async (id) => {
    try {
      await api.deleteSavedQuery(id)
      setSavedQueries(prev => prev.filter(q => q.id !== id))
    } catch {}
  }

  const exportCsv = async () => {
    try {
      const resp = await fetch(`/api/fleet/query?q=${encodeURIComponent(queryExpr)}&format=csv`)
      const text = await resp.text()
      const blob = new Blob([text], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'fleet_query.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch {}
  }

  const runBulkAction = async (action, params = {}) => {
    if (!queryExpr.trim()) return
    try {
      const result = await api.fleetQueryBulkAction(queryExpr, action, params)
      alert(`Bulk ${action}: ${result.succeeded}/${result.total_matched} succeeded`)
      setShowBulkAction(false)
    } catch (e) {
      alert(`Bulk action failed: ${e.message}`)
    }
  }

  // Autocomplete suggestions based on cursor position
  const getAutocompleteSuggestions = () => {
    const val = queryExpr.trim()
    const parts = val.split(/\s+/)
    const last = parts[parts.length - 1]?.toLowerCase() || ''
    if (!last) return Object.keys(queryFields)
    return Object.keys(queryFields).filter(f => f.startsWith(last))
  }

  return (
    <div className="bg-card border border-main rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Search className="w-4 h-4 text-zinc-500 shrink-0" />
        <div className="relative flex-1">
          <input
            ref={queryInputRef}
            type="text"
            placeholder='Fleet query — e.g. battery < 20 AND online = true'
            value={queryExpr}
            onChange={(e) => {
              setQueryExpr(e.target.value)
              setShowAutocomplete(true)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { executeQuery(); setShowAutocomplete(false) }
              if (e.key === 'Escape') { setShowAutocomplete(false) }
            }}
            onFocus={() => setShowAutocomplete(true)}
            onBlur={() => setTimeout(() => setShowAutocomplete(false), 200)}
            className="w-full bg-black border border-main px-3 py-1.5 text-xs mono rounded focus:outline-none focus:border-zinc-500"
          />
          {showAutocomplete && queryExpr && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-zinc-900 border border-main rounded shadow-lg z-20 max-h-48 overflow-y-auto">
              {getAutocompleteSuggestions().map(field => (
                <button
                  key={field}
                  className="w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-800 flex justify-between"
                  onMouseDown={() => {
                    const parts = queryExpr.split(/\s+/)
                    parts[parts.length - 1] = field
                    setQueryExpr(parts.join(' ') + ' ')
                    setShowAutocomplete(false)
                    queryInputRef.current?.focus()
                  }}
                >
                  <span className="mono text-zinc-200">{field}</span>
                  <span className="text-zinc-600 text-[10px]">{queryFields[field]}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={() => executeQuery()}
          disabled={queryLoading || !queryExpr.trim()}
          className="bg-white text-black text-xs font-bold px-3 py-1.5 rounded hover:bg-zinc-200 transition-colors disabled:opacity-40 flex items-center gap-1.5"
        >
          <Play className="w-3 h-3" />
          {queryLoading ? 'Running...' : 'Run'}
        </button>
        {queryActive && (
          <button
            onClick={clearQuery}
            className="text-zinc-500 hover:text-white text-xs px-2 py-1.5 rounded border border-main hover:border-zinc-600 transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {/* Query toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Presets dropdown */}
        <div className="relative" ref={presetsRef}>
          <button
            onClick={() => { setShowPresets(!showPresets); setShowSaved(false) }}
            className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 border border-main px-2 py-1 rounded transition-colors"
          >
            <Zap className="w-3 h-3" /> Presets <ChevronDown className="w-2.5 h-2.5" />
          </button>
          {showPresets && (
            <div className="absolute top-full left-0 mt-1 bg-zinc-900 border border-main rounded shadow-lg z-20 w-64">
              {presetQueries.map((p, i) => (
                <button
                  key={i}
                  className="w-full text-left px-3 py-2 text-xs hover:bg-zinc-800 border-b border-main last:border-0"
                  onClick={() => { setQueryExpr(p.expression); setShowPresets(false); executeQuery(p.expression) }}
                >
                  <span className="text-zinc-200 font-medium">{p.name}</span>
                  <span className="block text-[10px] text-zinc-600 mono mt-0.5">{p.expression}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Saved queries dropdown */}
        <div className="relative" ref={savedRef}>
          <button
            onClick={() => { setShowSaved(!showSaved); setShowPresets(false) }}
            className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 border border-main px-2 py-1 rounded transition-colors"
          >
            <Save className="w-3 h-3" /> Saved <ChevronDown className="w-2.5 h-2.5" />
          </button>
          {showSaved && (
            <div className="absolute top-full left-0 mt-1 bg-zinc-900 border border-main rounded shadow-lg z-20 w-72">
              {savedQueries.length === 0 && (
                <p className="px-3 py-2 text-[10px] text-zinc-600">No saved queries</p>
              )}
              {savedQueries.map(q => (
                <div key={q.id} className="flex items-center border-b border-main last:border-0">
                  <button
                    className="flex-1 text-left px-3 py-2 text-xs hover:bg-zinc-800"
                    onClick={() => { setQueryExpr(q.expression); setShowSaved(false); executeQuery(q.expression) }}
                  >
                    <span className="text-zinc-200 font-medium">{q.name}</span>
                    <span className="block text-[10px] text-zinc-600 mono mt-0.5">{q.expression}</span>
                  </button>
                  <button
                    onClick={() => deleteSavedQuery(q.id)}
                    className="p-2 text-zinc-600 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {queryExpr.trim() && (
          <>
            <button
              onClick={saveCurrentQuery}
              className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 border border-main px-2 py-1 rounded transition-colors"
            >
              <BookmarkPlus className="w-3 h-3" /> Save Query
            </button>
            {queryActive && (
              <>
                <button
                  onClick={exportCsv}
                  className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 border border-main px-2 py-1 rounded transition-colors"
                >
                  <Download className="w-3 h-3" /> Export CSV
                </button>
                <div className="relative">
                  <button
                    onClick={() => setShowBulkAction(!showBulkAction)}
                    className="flex items-center gap-1 text-[10px] text-amber-500 hover:text-amber-300 border border-amber-900/50 px-2 py-1 rounded transition-colors"
                  >
                    <Zap className="w-3 h-3" /> Bulk Action <ChevronDown className="w-2.5 h-2.5" />
                  </button>
                  {showBulkAction && (
                    <div className="absolute top-full left-0 mt-1 bg-zinc-900 border border-main rounded shadow-lg z-20 w-48">
                      {['reboot', 'lock', 'unlock', 'add_tag', 'add_to_group'].map(action => (
                        <button
                          key={action}
                          className="w-full text-left px-3 py-2 text-xs hover:bg-zinc-800 border-b border-main last:border-0 text-zinc-300"
                          onClick={() => {
                            let params = {}
                            if (action === 'add_tag') {
                              const tag = prompt('Tag name:')
                              if (!tag) return
                              params = { tag }
                            }
                            if (action === 'add_to_group') {
                              const gid = prompt('Group ID:')
                              if (!gid) return
                              params = { group_id: gid }
                            }
                            runBulkAction(action, params)
                          }}
                        >
                          {action.replace(/_/g, ' ')}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </>
        )}

        {queryActive && queryMatches && (
          <span className="text-[10px] text-zinc-500 ml-auto">
            {queryMatches.length} device{queryMatches.length !== 1 ? 's' : ''} matched
          </span>
        )}
      </div>

      {queryError && (
        <div className="bg-red-950/50 border border-red-900/50 rounded p-2 text-xs text-red-400 mono">
          {queryError}
        </div>
      )}
    </div>
  )
}
