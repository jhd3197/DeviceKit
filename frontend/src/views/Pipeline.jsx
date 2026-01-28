import React, { useState, useEffect, useCallback } from 'react'
import {
  Play,
  Check,
  X,
  Clock,
  CheckCircle,
  XCircle,
} from 'lucide-react'
import { api } from '../api'

// Demo data for when backend has no builds
const DEMO_BUILDS = [
  {
    id: '842',
    number: 842,
    title: 'Regression Suite: SamanLabs API v4',
    status: 'completed',
    created_at: Date.now() / 1000 - 120,
    success_rate: 98.2,
    tests: [
      { id: '001', name: 'test_login_success_flow', status: 'pass', device: 'MOTO-G1', duration: 42 },
      { id: '002', name: 'test_payment_gateway_callback', status: 'fail', device: 'SAM-A14', duration: 0 },
      { id: '003', name: 'test_image_upload_latency', status: 'running', device: 'PIX-LAB', duration: 0 },
      { id: '004', name: 'test_session_persistence', status: 'pass', device: 'MOTO-G1', duration: 18 },
      { id: '005', name: 'test_push_notification_delivery', status: 'pass', device: 'SAM-A14', duration: 31 },
    ],
    failures: [
      {
        test_id: '002',
        test_name: 'test_payment_gateway_callback',
        error: 'AssertionError: Expected 200, got 500',
        trace:
          '> at node_modules/samanlabs-sdk/api.js:42:12\n> at test_payment_gateway_callback (tests/billing_test.js:104:5)\n\n--- Device Context ---\nModel: Samsung A14 | OS: 12.1 | Free Memory: 1.2GB',
      },
    ],
  },
]

export default function Pipeline() {
  const [builds, setBuilds] = useState(DEMO_BUILDS)
  const [selectedBuild, setSelectedBuild] = useState(DEMO_BUILDS[0])
  const [searchFilter, setSearchFilter] = useState('')
  const [selectedFailure, setSelectedFailure] = useState(
    DEMO_BUILDS[0]?.failures?.[0] || null
  )

  const fetchBuilds = useCallback(async () => {
    try {
      const res = await api.getBuilds()
      if (res.builds && res.builds.length > 0) {
        setBuilds(res.builds)
      }
    } catch {
      // keep demo data
    }
  }, [])

  useEffect(() => {
    fetchBuilds()
  }, [fetchBuilds])

  const handleNewRun = async () => {
    try {
      const build = await api.startBuild()
      setBuilds((prev) => [build, ...prev])
      setSelectedBuild(build)
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
  const passCount = tests.filter((t) => t.status === 'pass').length
  const failCount = tests.filter((t) => t.status === 'fail').length

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
            {filteredBuilds.map((build) => {
              const bp = build.tests?.filter((t) => t.status === 'pass').length || 0
              const bf = build.tests?.filter((t) => t.status === 'fail').length || 0
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
                    <span className="text-[10px] mono text-emerald-500 font-bold uppercase">
                      Build #{build.number}
                    </span>
                    <span className="text-[10px] text-zinc-500">
                      {timeAgo(build.created_at)}
                    </span>
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
                      <Clock className="w-3 h-3 text-blue-500" /> 12s
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Build detail */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Metrics row */}
          <div className="p-6 border-b border-main grid grid-cols-4 gap-6 bg-zinc-950 shrink-0">
            <PipelineMetric
              label="Success Rate"
              value={`${selectedBuild?.success_rate ?? 0}%`}
              valueClass="text-emerald-500"
            />
            <PipelineMetric label="Active Nodes" value={`${passCount + failCount}/${builds.length}`} />
            <PipelineMetric label="Runtime" value="04:22:01" />
            <PipelineMetric
              label="Build ID"
              value={`#${selectedBuild?.number || '--'}`}
              valueClass="text-zinc-400"
              mono
            />
          </div>

          {/* Test results stream */}
          <div className="flex-1 overflow-y-auto p-6 space-y-2 bg-[#020202]">
            <h3 className="text-[10px] font-bold text-zinc-600 uppercase mb-4">
              Execution Stream
            </h3>
            {tests.map((test) => (
              <div
                key={test.id}
                className={`bg-zinc-900/20 p-3 rounded text-xs flex justify-between items-center ${
                  test.status === 'pass'
                    ? 'test-pass'
                    : test.status === 'fail'
                    ? 'test-fail'
                    : 'test-running'
                }`}
              >
                <div className="flex items-center gap-3">
                  {test.status === 'pass' && <Check className="w-3 h-3" />}
                  {test.status === 'fail' && <X className="w-3 h-3" />}
                  {test.status === 'running' && (
                    <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                  )}
                  <span className="mono text-zinc-500 text-[10px]">#{test.id}</span>
                  <span className="font-medium">{test.name}</span>
                </div>
                <span className="text-[10px] mono text-zinc-600">
                  {test.status === 'fail' ? (
                    <span
                      className="font-bold bg-red-500/10 px-2 py-0.5 rounded text-red-400 cursor-pointer"
                      onClick={() =>
                        setSelectedFailure(
                          failures.find((f) => f.test_id === test.id) || null
                        )
                      }
                    >
                      STACK_TRACE_AVAIL
                    </span>
                  ) : test.status === 'running' ? (
                    <span className="text-blue-400 italic">Processing...</span>
                  ) : (
                    `${test.device} [${test.duration}ms]`
                  )}
                </span>
              </div>
            ))}
          </div>

          {/* Failure analysis panel */}
          <div className="h-48 border-t border-main bg-black p-4 flex flex-col shrink-0">
            <div className="flex justify-between items-center mb-2">
              <p className="text-[10px] font-bold text-red-500 uppercase tracking-widest">
                {selectedFailure
                  ? `Failure Analysis: #${selectedFailure.test_id}`
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
    </>
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
