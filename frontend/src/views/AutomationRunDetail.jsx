import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  CheckCircle,
  XCircle,
  Loader,
  Square,
  Clock,
  SkipForward,
  AlertTriangle,
  HeartPulse,
  Image,
  Eye,
  FileBarChart,
  Package,
  BrainCircuit,
  Share2,
  Download,
} from 'lucide-react'
import { api } from '../api'
import ExtensionSlot from '../extensions/ExtensionSlot'

const POLL_INTERVAL = 1500

export default function AutomationRunDetail() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const [run, setRun] = useState(null)
  const [loading, setLoading] = useState(true)
  const intervalRef = useRef(null)
  const [screenshotOverlay, setScreenshotOverlay] = useState(null)
  const [regressionReport, setRegressionReport] = useState(null)
  const [showRegressionReport, setShowRegressionReport] = useState(false)
  const [diffOverlay, setDiffOverlay] = useState(null) // { baselineUrl, currentB64, diffRegions, ssim, verdict }
  const [bundleAnalyses, setBundleAnalyses] = useState({}) // bundle_id -> {loading, data, error}
  const [shareLinks, setShareLinks] = useState({}) // bundle_id -> {token, url}

  const fetchRun = useCallback(async () => {
    try {
      const data = await api.getAutomationRun(runId)
      setRun(data)
      return data
    } catch (e) {
      console.error('Failed to fetch run:', e)
      return null
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    fetchRun().then((data) => {
      if (data?.status === 'running') {
        intervalRef.current = setInterval(async () => {
          const updated = await fetchRun()
          if (updated && updated.status !== 'running') {
            clearInterval(intervalRef.current)
            // Fetch regression report when run completes
            api.getRegressionReport(runId).then(setRegressionReport).catch(() => {})
          }
        }, POLL_INTERVAL)
      } else if (data) {
        // Already finished — fetch report
        api.getRegressionReport(runId).then(setRegressionReport).catch(() => {})
      }
    })
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchRun, runId])

  const handleCancel = async () => {
    try {
      await api.cancelAutomationRun(runId)
      fetchRun()
    } catch (e) {
      console.error('Failed to cancel:', e)
    }
  }

  const handleAnalyzeBundle = async (bundleId) => {
    setBundleAnalyses(prev => ({ ...prev, [bundleId]: { loading: true } }))
    try {
      const result = await api.analyzeDebugBundle(bundleId)
      setBundleAnalyses(prev => ({ ...prev, [bundleId]: { loading: false, data: result } }))
    } catch (e) {
      setBundleAnalyses(prev => ({ ...prev, [bundleId]: { loading: false, error: e.message } }))
    }
  }

  const handleShareBundle = async (bundleId) => {
    try {
      const result = await api.shareDebugBundle(bundleId)
      const url = api.sharedBundleUrl(result.token)
      setShareLinks(prev => ({ ...prev, [bundleId]: { token: result.token, url } }))
      navigator.clipboard?.writeText(url)
    } catch {}
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">
        Loading...
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">
        Run not found.
      </div>
    )
  }

  const totalSteps = run.total_steps || 0
  const completedSteps = run.completed_steps || 0
  const progress = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0
  const stepResults = run.step_results || []

  const statusConfig = {
    running: { color: 'text-blue-400', bg: 'bg-blue-500/10', label: 'Running' },
    completed: {
      color: 'text-emerald-400',
      bg: 'bg-emerald-500/10',
      label: 'Completed',
    },
    failed: { color: 'text-red-400', bg: 'bg-red-500/10', label: 'Failed' },
    cancelled: {
      color: 'text-zinc-400',
      bg: 'bg-zinc-500/10',
      label: 'Cancelled',
    },
  }
  const sc = statusConfig[run.status] || statusConfig.cancelled

  return (
    <>
      {/* Header */}
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-body shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/automations')}
            className="text-zinc-400 hover:text-strong transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <h2 className="text-sm font-bold uppercase tracking-widest text-zinc-400">
            Run Detail
          </h2>
        </div>
        {run.status === 'running' && (
          <button
            onClick={handleCancel}
            className="bg-red-600 hover:bg-red-500 text-white text-xs font-bold px-4 py-1.5 rounded transition-colors flex items-center gap-2"
          >
            <Square className="w-3 h-3 fill-current" /> Cancel
          </button>
        )}
      </header>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Status bar */}
        <div className="bg-card border border-main rounded p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <span
                className={`text-xs font-bold uppercase px-2 py-0.5 rounded ${sc.bg} ${sc.color}`}
              >
                {sc.label}
              </span>
              <span className="text-xs text-zinc-300 font-medium">
                {run.automation_name}
              </span>
              {run.self_heal && (
                <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-amber-500/10 text-amber-400">
                  Self-heal on
                </span>
              )}
            </div>
            <span className="text-[10px] mono text-zinc-500">
              Device: {run.device_id}
            </span>
          </div>

          {/* Progress bar */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  run.status === 'failed'
                    ? 'bg-red-500'
                    : run.status === 'completed'
                      ? 'bg-emerald-500'
                      : 'bg-blue-500'
                }`}
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="text-[10px] mono text-zinc-400 shrink-0">
              {completedSteps}/{totalSteps}
            </span>
          </div>

          {/* Timing */}
          <div className="flex gap-6 mt-3 text-[10px] text-zinc-500">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              Started: {run.started_at ? new Date(Number(run.started_at) * 1000).toLocaleTimeString() : '--'}
            </span>
            {run.finished_at && (
              <span>
                Duration:{' '}
                {((Number(run.finished_at) - Number(run.started_at)) * 1000).toFixed(0)}ms
              </span>
            )}
          </div>
        </div>

        {/* Step results */}
        <div>
          <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-3">
            Step Results
          </h3>
          <div className="space-y-1">
            {stepResults.length === 0 && run.status === 'running' ? (
              <div className="bg-card border border-main rounded p-4 text-center text-zinc-600 text-xs flex items-center justify-center gap-2">
                <Loader className="w-3 h-3 animate-spin" /> Waiting for
                first step...
              </div>
            ) : (
              stepResults.map((sr, idx) => (
                <div
                  key={sr.step_id || idx}
                  className={`bg-card border border-main rounded p-3 text-xs ${
                    sr.status === 'completed'
                      ? 'step-completed'
                      : sr.status === 'failed'
                        ? 'step-failed'
                        : sr.status === 'running'
                          ? 'step-running'
                          : 'step-skipped'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <StepStatusIcon status={sr.status} />
                      <span className="mono text-zinc-500 text-[10px]">
                        #{idx + 1}
                      </span>
                      <span className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded uppercase font-bold">
                        {sr.step_type}
                      </span>
                      {sr.label && (
                        <span className="text-zinc-300">{sr.label}</span>
                      )}
                      {/* Self-healed badge */}
                      {sr.healed === true && (
                        <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 flex items-center gap-1">
                          <HeartPulse className="w-3 h-3" /> Self-healed
                        </span>
                      )}
                      {sr.healed === false && sr.heal_reasoning && (
                        <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-red-500/10 text-red-400 flex items-center gap-1">
                          <HeartPulse className="w-3 h-3" /> Heal failed
                        </span>
                      )}
                      {/* Visual assertion badge */}
                      {sr.step_type === 'screenshot_assert' && sr.status === 'completed' && (
                        <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-violet-500/10 text-violet-400 flex items-center gap-1">
                          <Eye className="w-3 h-3" /> Visual pass
                        </span>
                      )}
                      {sr.step_type === 'screenshot_assert' && sr.status === 'failed' && (
                        <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-red-500/10 text-red-400 flex items-center gap-1">
                          <Eye className="w-3 h-3" /> Visual fail
                        </span>
                      )}
                    </div>
                    <span className="mono text-zinc-600 text-[10px]">
                      {sr.duration_ms > 0 ? `${sr.duration_ms}ms` : ''}
                    </span>
                  </div>
                  {sr.output && (
                    <p className="mt-1.5 text-[10px] text-zinc-500 mono pl-8">
                      {sr.output}
                    </p>
                  )}
                  {sr.error && (
                    <p className="mt-1.5 text-[10px] text-red-400 mono pl-8">
                      {sr.error}
                    </p>
                  )}

                  {/* Self-heal details */}
                  {sr.healed === true && (
                    <div className="mt-2 ml-8 bg-amber-500/5 border border-amber-500/20 rounded p-2.5 space-y-1.5">
                      {sr.heal_reasoning && (
                        <p className="text-[10px] text-amber-300">{sr.heal_reasoning}</p>
                      )}
                      {sr.original_step && sr.healed_step && (
                        <div className="flex gap-4 text-[10px] mono">
                          <div>
                            <span className="text-zinc-500 block mb-0.5">Original:</span>
                            <span className="text-zinc-400">
                              {sr.original_step.type} &mdash; {JSON.stringify(sr.original_step.config)}
                            </span>
                          </div>
                          <div>
                            <span className="text-amber-400 block mb-0.5">Healed:</span>
                            <span className="text-amber-300">
                              {sr.healed_step.type} &mdash; {JSON.stringify(sr.healed_step.config)}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {sr.healed === false && sr.heal_reasoning && (
                    <div className="mt-2 ml-8 bg-red-500/5 border border-red-500/20 rounded p-2.5">
                      <p className="text-[10px] text-red-300">
                        Heal attempted but failed: {sr.heal_reasoning}
                      </p>
                    </div>
                  )}

                  {sr.failure_screenshot && (
                    <div className="mt-2 pl-8">
                      <img
                        src={api.getFailureScreenshotUrl(runId, idx)}
                        alt="Failure screenshot"
                        className="w-6 h-auto rounded border border-red-500/30 cursor-pointer hover:border-red-400 transition-colors"
                        onClick={() => setScreenshotOverlay(api.getFailureScreenshotUrl(runId, idx))}
                      />
                    </div>
                  )}

                  {/* Debug Bundle controls */}
                  {sr.debug_bundle_id && (
                    <div className="mt-2 ml-8 bg-orange-500/5 border border-orange-500/20 rounded p-3 space-y-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Package className="w-3.5 h-3.5 text-orange-400 shrink-0" />
                        <span className="text-[10px] font-bold text-orange-400 uppercase">Debug Bundle</span>

                        <a
                          href={api.downloadDebugBundleUrl(sr.debug_bundle_id)}
                          className="ml-auto flex items-center gap-1 text-[10px] text-zinc-400 hover:text-strong border border-main px-2 py-0.5 rounded transition-colors"
                          download
                        >
                          <Download className="w-3 h-3" /> Download ZIP
                        </a>

                        <button
                          onClick={() => handleAnalyzeBundle(sr.debug_bundle_id)}
                          disabled={bundleAnalyses[sr.debug_bundle_id]?.loading}
                          className="flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300 border border-blue-500/30 px-2 py-0.5 rounded transition-colors disabled:opacity-50"
                        >
                          <BrainCircuit className="w-3 h-3" />
                          {bundleAnalyses[sr.debug_bundle_id]?.loading ? 'Analyzing...' : 'AI Analysis'}
                        </button>

                        <button
                          onClick={() => handleShareBundle(sr.debug_bundle_id)}
                          className="flex items-center gap-1 text-[10px] text-zinc-400 hover:text-strong border border-main px-2 py-0.5 rounded transition-colors"
                        >
                          <Share2 className="w-3 h-3" /> Share
                        </button>
                      </div>

                      {/* Share link result */}
                      {shareLinks[sr.debug_bundle_id] && (
                        <div className="text-[10px] mono text-zinc-500 bg-black/30 rounded p-1.5 break-all">
                          Link copied: {shareLinks[sr.debug_bundle_id].url}
                        </div>
                      )}

                      {/* AI Analysis result */}
                      {bundleAnalyses[sr.debug_bundle_id]?.loading && (
                        <div className="flex items-center gap-2 text-[10px] text-blue-400">
                          <Loader className="w-3 h-3 animate-spin" /> Running AI analysis on bundle contents...
                        </div>
                      )}
                      {bundleAnalyses[sr.debug_bundle_id]?.data && (
                        <div className="bg-blue-500/5 border border-blue-500/20 rounded p-2.5">
                          <p className="text-[10px] font-bold text-blue-400 uppercase mb-1 flex items-center gap-1">
                            <BrainCircuit className="w-3 h-3" /> AI Root Cause Analysis
                          </p>
                          <pre className="text-[10px] text-zinc-300 whitespace-pre-wrap font-mono leading-relaxed">
                            {bundleAnalyses[sr.debug_bundle_id].data.analysis || JSON.stringify(bundleAnalyses[sr.debug_bundle_id].data, null, 2)}
                          </pre>
                        </div>
                      )}
                      {bundleAnalyses[sr.debug_bundle_id]?.error && (
                        <div className="text-[10px] text-red-400">
                          Analysis failed: {bundleAnalyses[sr.debug_bundle_id].error}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}

            {/* Show pending steps indicator while running */}
            {run.status === 'running' &&
              stepResults.length < totalSteps && (
                <div className="bg-card border border-main rounded p-3 text-xs step-running flex items-center gap-3">
                  <Loader className="w-3 h-3 text-blue-400 animate-spin" />
                  <span className="text-zinc-500">
                    Step {stepResults.length + 1} of {totalSteps} executing...
                  </span>
                </div>
              )}
          </div>
        </div>

        {/* Visual Regression Report */}
        {regressionReport && regressionReport.total_assertions > 0 && (
          <div className="bg-card border border-main rounded overflow-hidden">
            <button
              onClick={() => setShowRegressionReport(!showRegressionReport)}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-zinc-900/30 transition-colors text-left"
            >
              <FileBarChart className="w-4 h-4 text-violet-400 shrink-0" />
              <span className="text-xs font-bold text-zinc-300 flex-1">
                Visual Regression Report
              </span>
              <div className="flex items-center gap-2 text-[10px]">
                <span className="text-emerald-400">{regressionReport.passed} passed</span>
                {regressionReport.failed > 0 && (
                  <span className="text-red-400">{regressionReport.failed} failed</span>
                )}
                {regressionReport.needs_review > 0 && (
                  <span className="text-amber-400">{regressionReport.needs_review} review</span>
                )}
              </div>
            </button>

            {showRegressionReport && (
              <div className="px-4 pb-4 border-t border-main space-y-2 pt-3">
                {/* Summary bar */}
                <div className="flex h-2 rounded-full overflow-hidden bg-zinc-800">
                  {regressionReport.passed > 0 && (
                    <div
                      className="bg-emerald-500"
                      style={{ width: `${(regressionReport.passed / regressionReport.total_assertions) * 100}%` }}
                    />
                  )}
                  {regressionReport.failed > 0 && (
                    <div
                      className="bg-red-500"
                      style={{ width: `${(regressionReport.failed / regressionReport.total_assertions) * 100}%` }}
                    />
                  )}
                  {regressionReport.needs_review > 0 && (
                    <div
                      className="bg-amber-500"
                      style={{ width: `${(regressionReport.needs_review / regressionReport.total_assertions) * 100}%` }}
                    />
                  )}
                </div>

                {/* Individual results */}
                {regressionReport.results.map((vr, i) => (
                  <div
                    key={i}
                    className={`flex items-center justify-between p-2 rounded text-[10px] ${
                      vr.verdict === 'pass'
                        ? 'bg-emerald-500/5 border border-emerald-500/20'
                        : vr.verdict === 'fail'
                          ? 'bg-red-500/5 border border-red-500/20'
                          : 'bg-amber-500/5 border border-amber-500/20'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Image className={`w-3 h-3 ${
                        vr.verdict === 'pass' ? 'text-emerald-400' : vr.verdict === 'fail' ? 'text-red-400' : 'text-amber-400'
                      }`} />
                      <span className="text-zinc-300">
                        Step {vr.step_index + 1}: {vr.step_label || 'Screenshot Assert'}
                      </span>
                    </div>
                    <span className={`font-bold uppercase ${
                      vr.verdict === 'pass' ? 'text-emerald-400' : vr.verdict === 'fail' ? 'text-red-400' : 'text-amber-400'
                    }`}>
                      {vr.verdict}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Error panel */}
        {run.error && (
          <div className="bg-red-500/5 border border-red-500/20 rounded p-4">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              <span className="text-xs font-bold text-red-400 uppercase">
                Execution Error
              </span>
            </div>
            <pre className="text-[10px] mono text-red-300 whitespace-pre-wrap">
              {run.error}
            </pre>
          </div>
        )}

        {/* Extension panels contributed to the run detail (plan 04) */}
        <ExtensionSlot name="run-detail.panels" className="space-y-6" run={run} />
      </div>

      {/* Failure screenshot overlay */}
      {screenshotOverlay && (
        <div
          className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 cursor-pointer"
          onClick={() => setScreenshotOverlay(null)}
        >
          <img
            src={screenshotOverlay}
            alt="Failure screenshot (full)"
            className="max-w-[90vw] max-h-[90vh] rounded-lg border border-zinc-700 shadow-2xl"
          />
        </div>
      )}
    </>
  )
}

function StepStatusIcon({ status }) {
  switch (status) {
    case 'completed':
      return <CheckCircle className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
    case 'failed':
      return <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />
    case 'running':
      return <Loader className="w-3.5 h-3.5 text-blue-400 animate-spin shrink-0" />
    case 'skipped':
      return <SkipForward className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
    default:
      return <Clock className="w-3.5 h-3.5 text-zinc-600 shrink-0" />
  }
}
