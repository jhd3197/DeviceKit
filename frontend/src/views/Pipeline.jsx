import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  Play,
  Check,
  X,
  Clock,
  CheckCircle,
  XCircle,
  ExternalLink,
  Loader2,
  Terminal,
  Image,
} from 'lucide-react'
import { api, subscribeToEvents } from '../api'

export default function Pipeline() {
  const [builds, setBuilds] = useState([])
  const [selectedBuild, setSelectedBuild] = useState(null)
  const [searchFilter, setSearchFilter] = useState('')
  const [selectedFailure, setSelectedFailure] = useState(null)
  const [loading, setLoading] = useState(true)
  const [screenshotModal, setScreenshotModal] = useState(null)
  const esRef = useRef(null)

  const fetchBuilds = useCallback(async () => {
    try {
      const res = await api.getBuilds()
      const list = res.builds || []
      setBuilds(list)
      if (!selectedBuild && list.length > 0) {
        setSelectedBuild(list[0])
        setSelectedFailure(list[0]?.failures?.[0] || null)
      }
    } catch {
      // keep current state
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch + polling
  useEffect(() => {
    fetchBuilds()
    const interval = setInterval(fetchBuilds, 5000)
    return () => clearInterval(interval)
  }, [fetchBuilds])

  // Refresh selected build detail when builds change
  useEffect(() => {
    if (!selectedBuild) return
    const updated = builds.find((b) => b.id === selectedBuild.id)
    if (updated) {
      setSelectedBuild(updated)
    }
  }, [builds])

  // SSE for real-time test results
  useEffect(() => {
    const es = subscribeToEvents({
      onPipelineTest: () => {
        fetchBuilds()
      },
      onPipelineBuild: () => {
        fetchBuilds()
      },
    })
    esRef.current = es
    return () => es.close()
  }, [fetchBuilds])

  const handleNewRun = async () => {
    try {
      const build = await api.startBuild()
      setBuilds((prev) => [build, ...prev])
      setSelectedBuild(build)
      setSelectedFailure(null)
    } catch (e) {
      console.error('Failed to start build:', e)
    }
  }

  const filteredBuilds = builds.filter(
    (b) =>
      b.title?.toLowerCase().includes(searchFilter.toLowerCase()) ||
      String(b.number).includes(searchFilter)
  )

  const tests = selectedBuild?.tests || []
  const failures = selectedBuild?.failures || []
  const passCount = selectedBuild?.passed ?? tests.filter((t) => t.status === 'pass').length
  const failCount = selectedBuild?.failed ?? tests.filter((t) => t.status === 'fail').length
  const errorCount = selectedBuild?.errors ?? 0
  const skippedCount = selectedBuild?.skipped ?? 0

  const successRate = selectedBuild?.success_rate ?? 0
  const durationMs = selectedBuild?.duration_ms
  const runtimeStr = durationMs != null
    ? formatDuration(durationMs)
    : selectedBuild?.started_at
      ? formatDuration((Date.now() / 1000 - selectedBuild.started_at) * 1000)
      : '--:--'

  const uniqueDevices = new Set(tests.map((t) => t.device).filter(Boolean))

  return (
    <>
      {/* Header */}
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-black shrink-0">
        <h2 className="text-sm font-bold uppercase tracking-widest text-zinc-400">
          Automation Pipeline
        </h2>
        <button
          onClick={handleNewRun}
          className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2"
        >
          <Play className="w-3 h-3 fill-current" /> New Run
        </button>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Build list sidebar */}
        <div className="w-1/3 border-r border-main flex flex-col bg-zinc-900/10">
          <div className="p-4 border-b border-main bg-zinc-900/20">
            <input
              type="text"
              placeholder="Search builds..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="w-full bg-black border border-main px-3 py-1.5 text-xs rounded focus:outline-none"
            />
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center p-8 text-zinc-500 text-xs">
                <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading builds...
              </div>
            ) : filteredBuilds.length === 0 ? (
              <div className="p-6 text-center text-zinc-600 text-xs space-y-3">
                <Terminal className="w-8 h-8 mx-auto text-zinc-700" />
                <p className="font-semibold text-zinc-400">No builds yet</p>
                <p>Run tests with the pytest-droidlink plugin:</p>
                <pre className="bg-zinc-900 p-3 rounded text-[10px] text-left text-emerald-500 overflow-x-auto">
{`pip install -e ./droidlink
pytest tests/ \\
  --device=SERIAL \\
  --devicekit-url=http://localhost:5050`}
                </pre>
              </div>
            ) : (
              filteredBuilds.map((build) => {
                const bp = build.passed ?? build.tests?.filter((t) => t.status === 'pass').length ?? 0
                const bf = build.failed ?? build.tests?.filter((t) => t.status === 'fail').length ?? 0
                const isSelected = selectedBuild?.id === build.id
                return (
                  <div
                    key={build.id}
                    onClick={() => {
                      setSelectedBuild(build)
                      setSelectedFailure(build.failures?.[0] || null)
                    }}
                    className={`p-4 border-b border-main cursor-pointer transition-colors ${
                      isSelected ? 'bg-zinc-900/40' : 'hover:bg-zinc-900/20'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex items-center gap-2">
                        <StatusBadge status={build.status} />
                        <span className="text-[10px] mono text-emerald-500 font-bold uppercase">
                          Build #{build.number}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {build.ci_url && (
                          <a
                            href={build.ci_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-zinc-500 hover:text-blue-400"
                          >
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        )}
                        <span className="text-[10px] text-zinc-500">
                          {timeAgo(build.created_at)}
                        </span>
                      </div>
                    </div>
                    <h4 className="text-xs font-semibold mb-2">{build.title}</h4>
                    <div className="flex gap-4">
                      <div className="flex items-center gap-1 text-[10px] text-zinc-400">
                        <CheckCircle className="w-3 h-3 text-emerald-500" /> {bp}
                      </div>
                      <div className="flex items-center gap-1 text-[10px] text-zinc-400">
                        <XCircle className="w-3 h-3 text-red-500" /> {bf}
                      </div>
                      <div className="flex items-center gap-1 text-[10px] text-zinc-400">
                        <Clock className="w-3 h-3 text-blue-500" />{' '}
                        {build.duration_ms != null ? formatDuration(build.duration_ms) : '...'}
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* Build detail */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Metrics row */}
          <div className="p-6 border-b border-main grid grid-cols-4 gap-6 bg-zinc-950 shrink-0">
            <PipelineMetric
              label="Success Rate"
              value={`${successRate}%`}
              valueClass="text-emerald-500"
            />
            <PipelineMetric
              label="Devices"
              value={`${uniqueDevices.size}`}
            />
            <PipelineMetric label="Runtime" value={runtimeStr} />
            <PipelineMetric
              label="Build ID"
              value={selectedBuild ? `#${selectedBuild.number}` : '--'}
              valueClass="text-zinc-400"
              mono
            />
          </div>

          {/* Stats bar */}
          {selectedBuild && (
            <div className="px-6 py-2 border-b border-main bg-zinc-950/50 flex gap-4 text-[10px] shrink-0">
              <span className="text-emerald-500">{passCount} passed</span>
              <span className="text-red-500">{failCount} failed</span>
              {errorCount > 0 && <span className="text-orange-500">{errorCount} errors</span>}
              {skippedCount > 0 && <span className="text-zinc-500">{skippedCount} skipped</span>}
              <span className="text-zinc-600">/ {tests.length} total</span>
              {selectedBuild.source && selectedBuild.source !== 'manual' && (
                <span className="text-zinc-600 ml-auto">via {selectedBuild.source}</span>
              )}
            </div>
          )}

          {/* Test results stream */}
          <div className="flex-1 overflow-y-auto p-6 space-y-2 bg-[#020202]">
            <h3 className="text-[10px] font-bold text-zinc-600 uppercase mb-4">
              Execution Stream
            </h3>
            {tests.length === 0 && selectedBuild && (
              <p className="text-xs text-zinc-600 italic">
                {selectedBuild.status === 'created'
                  ? 'Waiting for tests to start...'
                  : selectedBuild.status === 'running'
                    ? 'Tests are running...'
                    : 'No tests recorded.'}
              </p>
            )}
            {tests.map((test, idx) => (
              <div
                key={test.id || idx}
                className={`bg-zinc-900/20 p-3 rounded text-xs flex justify-between items-center ${
                  test.status === 'pass'
                    ? 'test-pass'
                    : test.status === 'fail' || test.status === 'error'
                      ? 'test-fail'
                      : test.status === 'skip'
                        ? 'opacity-50'
                        : 'test-running'
                }`}
              >
                <div className="flex items-center gap-3">
                  {test.status === 'pass' && <Check className="w-3 h-3 text-emerald-500" />}
                  {(test.status === 'fail' || test.status === 'error') && (
                    <X className="w-3 h-3 text-red-500" />
                  )}
                  {test.status === 'skip' && (
                    <span className="w-3 h-3 text-zinc-500 text-center text-[10px]">-</span>
                  )}
                  {test.status === 'running' && (
                    <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                  )}
                  <span className="font-medium">{test.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  {test.device && (
                    <span className="text-[10px] mono text-zinc-600">{test.device}</span>
                  )}
                  {(test.status === 'fail' || test.status === 'error') ? (
                    <div className="flex items-center gap-1">
                      {test.screenshot_b64 && (
                        <button
                          onClick={() => setScreenshotModal({
                            buildId: selectedBuild.id,
                            testIndex: idx,
                          })}
                          className="text-[10px] text-blue-400 hover:text-blue-300"
                        >
                          <Image className="w-3 h-3" />
                        </button>
                      )}
                      <span
                        className="font-bold bg-red-500/10 px-2 py-0.5 rounded text-red-400 cursor-pointer text-[10px]"
                        onClick={() =>
                          setSelectedFailure(
                            failures.find((f) => f.test_id === test.id) || null
                          )
                        }
                      >
                        STACK_TRACE_AVAIL
                      </span>
                    </div>
                  ) : test.status === 'running' ? (
                    <span className="text-blue-400 italic text-[10px]">Processing...</span>
                  ) : (
                    <span className="text-[10px] mono text-zinc-600">
                      {test.duration ? `${test.duration}ms` : ''}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Failure analysis panel */}
          <div className="h-48 border-t border-main bg-black p-4 flex flex-col shrink-0">
            <div className="flex justify-between items-center mb-2">
              <p className="text-[10px] font-bold text-red-500 uppercase tracking-widest">
                {selectedFailure
                  ? `Failure Analysis: ${selectedFailure.test_name || '#' + selectedFailure.test_id}`
                  : 'No Failure Selected'}
              </p>
              {selectedFailure && (
                <button
                  onClick={() => navigator.clipboard?.writeText(selectedFailure.trace || '')}
                  className="text-[10px] bg-zinc-900 px-2 py-1 rounded border border-main text-zinc-400"
                >
                  Copy Trace
                </button>
              )}
            </div>
            <div className="flex-1 bg-[#050505] rounded border border-main p-3 overflow-y-auto mono text-[10px] text-zinc-500 leading-relaxed">
              {selectedFailure ? (
                <>
                  <p className="text-red-400">{selectedFailure.error}</p>
                  <pre className="whitespace-pre-wrap mt-1">{selectedFailure.trace}</pre>
                </>
              ) : (
                <p className="text-zinc-700">Select a failed test to view analysis.</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Screenshot modal */}
      {screenshotModal && (
        <div
          className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center"
          onClick={() => setScreenshotModal(null)}
        >
          <div
            className="bg-zinc-900 rounded-lg border border-main p-4 max-w-2xl max-h-[80vh] overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-3">
              <p className="text-xs font-bold text-zinc-400">Failure Screenshot</p>
              <button
                onClick={() => setScreenshotModal(null)}
                className="text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <img
              src={api.getBuildScreenshot(screenshotModal.buildId, screenshotModal.testIndex)}
              alt="Failure screenshot"
              className="max-w-full rounded"
            />
          </div>
        </div>
      )}
    </>
  )
}

function StatusBadge({ status }) {
  const styles = {
    created: 'bg-zinc-600',
    running: 'bg-blue-500 animate-pulse',
    completed: 'bg-emerald-500',
    failed: 'bg-red-500',
  }
  return (
    <span className={`w-2 h-2 rounded-full inline-block ${styles[status] || 'bg-zinc-600'}`} />
  )
}

function PipelineMetric({ label, value, valueClass = '', mono }) {
  return (
    <div className="bg-black/40 border border-main p-3 rounded">
      <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">{label}</p>
      <p className={`text-xl font-bold italic ${valueClass} ${mono ? 'mono' : ''}`}>
        {value}
      </p>
    </div>
  )
}

function timeAgo(ts) {
  if (!ts) return ''
  const diff = Math.floor(Date.now() / 1000 - ts)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function formatDuration(ms) {
  if (ms == null) return '--:--'
  const totalSec = Math.floor(ms / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  if (h > 0) return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
