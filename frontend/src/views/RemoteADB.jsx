import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  Layers,
  LayoutGrid,
  Smartphone,
  Terminal,
  FolderTree,
  Folder,
  FileText,
  UploadCloud,
  Search,
  Download,
} from 'lucide-react'
import { api } from '../api'

export default function RemoteADB() {
  const [activeTab, setActiveTab] = useState('shell')
  const [shellHistory, setShellHistory] = useState([
    { type: 'comment', text: '# devicekit-adb v1.0.0' },
    { type: 'comment', text: '# Connected to remote device. Waiting for shell...' },
  ])
  const [shellInput, setShellInput] = useState('')
  const [devices, setDevices] = useState([])
  const [activeDevice, setActiveDevice] = useState(null)
  const [files, setFiles] = useState([])
  const [filePath, setFilePath] = useState('/sdcard')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef(null)
  const shellRef = useRef(null)

  const fetchDevices = useCallback(async () => {
    try {
      const res = await api.getDevices()
      setDevices(res.devices || [])
      if (!activeDevice && res.devices?.length > 0) {
        setActiveDevice(res.devices[0])
      }
    } catch {
      // silent
    }
  }, [activeDevice])

  const fetchFiles = useCallback(async () => {
    if (!activeDevice) return
    try {
      const res = await api.getFiles(activeDevice.device_id, filePath)
      setFiles(res.entries || [])
    } catch {
      // silent
    }
  }, [activeDevice, filePath])

  const handleSearch = useCallback(async () => {
    if (!activeDevice || !searchQuery.trim()) {
      setSearchResults(null)
      return
    }
    try {
      const res = await api.searchFiles(activeDevice.device_id, searchQuery.trim(), filePath)
      setSearchResults(res.results || [])
    } catch {
      setSearchResults([])
    }
  }, [activeDevice, searchQuery, filePath])

  const handleUpload = useCallback(async (file) => {
    if (!activeDevice || !file) return
    setUploading(true)
    try {
      const remotePath = `${filePath}/${file.name}`.replace(/\/+/g, '/')
      await api.uploadFile(activeDevice.device_id, file, remotePath)
      fetchFiles()
    } catch {
      // silent
    } finally {
      setUploading(false)
    }
  }, [activeDevice, filePath, fetchFiles])

  const handleDownload = useCallback((path) => {
    if (!activeDevice) return
    const url = api.downloadFileUrl(activeDevice.device_id, path)
    window.open(url, '_blank')
  }, [activeDevice])

  useEffect(() => {
    fetchDevices()
  }, [fetchDevices])

  useEffect(() => {
    fetchFiles()
  }, [fetchFiles])

  useEffect(() => {
    if (shellRef.current) {
      shellRef.current.scrollTop = shellRef.current.scrollHeight
    }
  }, [shellHistory])

  const deviceId = activeDevice?.device_id

  const runCommand = async () => {
    const cmd = shellInput.trim()
    if (!cmd || !deviceId) return
    setShellHistory((h) => [
      ...h,
      { type: 'prompt', text: `shell@saman-device:/ $ ${cmd}` },
    ])
    setShellInput('')
    try {
      const res = await api.runAdb(deviceId, cmd)
      setShellHistory((h) => [
        ...h,
        { type: 'output', text: res.output || '(no output)' },
      ])
    } catch (e) {
      setShellHistory((h) => [
        ...h,
        { type: 'error', text: `Error: ${e.message}` },
      ])
    }
  }

  const presets = [
    { label: 'SCREEN_DUMP', cmd: 'screencap -p /sdcard/screen.png' },
    { label: 'DUMPSYS_BATT', cmd: 'dumpsys battery' },
    { label: 'LOGCAT_CLEAR', cmd: 'logcat -c' },
    { label: 'REBOOT_LOADER', cmd: 'reboot bootloader' },
  ]

  const tabs = [
    { id: 'shell', label: 'Interactive Shell' },
    { id: 'logcat', label: 'Logcat Stream' },
    { id: 'network', label: 'Network Sniffer' },
  ]

  return (
    <>
      {/* Header */}
      <header className="h-12 border-b border-main flex items-center justify-between px-6 bg-black shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
              Active Node:
            </span>
            <span className="text-xs mono font-bold text-emerald-500">
              {deviceId || 'NONE'}
            </span>
          </div>
          <div className="h-4 w-[1px] bg-zinc-800" />
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
              Connection:
            </span>
            <span className="text-xs mono text-zinc-300">
              {activeDevice ? `tcp://${deviceId}:5555` : '--'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-bold text-zinc-600 uppercase">
            Latency: 4ms
          </span>
          <button className="bg-zinc-900 border border-main text-zinc-400 px-3 py-1 rounded text-[10px] font-bold hover:text-white transition-all">
            RESTART ADB SERVER
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Terminal area */}
        <div className="flex-1 flex flex-col border-r border-main">
          {/* Tabs */}
          <div className="flex bg-zinc-950 px-4 border-b border-main shrink-0">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 text-[10px] font-bold uppercase tracking-widest transition-colors ${
                  activeTab === tab.id
                    ? 'tab-active'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Terminal content */}
          <div
            ref={shellRef}
            className="flex-1 terminal-bg p-6 mono text-xs leading-relaxed overflow-y-auto"
          >
            {shellHistory.map((entry, i) => (
              <p
                key={i}
                className={
                  entry.type === 'comment'
                    ? 'text-zinc-500'
                    : entry.type === 'prompt'
                    ? 'text-zinc-300 mt-1'
                    : entry.type === 'error'
                    ? 'text-red-400'
                    : entry.type === 'success'
                    ? 'text-emerald-500'
                    : 'text-zinc-400 whitespace-pre-wrap'
                }
              >
                {entry.text}
              </p>
            ))}
            <div className="mt-4 flex gap-2">
              <span className="text-emerald-500 font-bold">$</span>
              <input
                type="text"
                value={shellInput}
                onChange={(e) => setShellInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && runCommand()}
                className="bg-transparent border-none outline-none flex-1 text-white caret-emerald-500"
                placeholder="Type adb command..."
                autoFocus
              />
            </div>
          </div>
        </div>

        {/* Right panel: Device Explorer + Presets */}
        <div className="w-96 bg-card-alt flex flex-col shrink-0">
          <div className="p-4 border-b border-main flex justify-between items-center bg-black">
            <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
              Device Explorer
            </h3>
            <div className="flex items-center gap-2">
              <UploadCloud
                className={`w-3.5 h-3.5 cursor-pointer ${uploading ? 'text-yellow-500 animate-pulse' : 'text-zinc-500 hover:text-emerald-500'}`}
                onClick={() => fileInputRef.current?.click()}
              />
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) handleUpload(file)
                  e.target.value = ''
                }}
              />
            </div>
          </div>

          {/* Search input */}
          <div className="px-4 pt-3 pb-2 border-b border-main bg-zinc-950">
            <div className="flex items-center gap-2 bg-zinc-900 border border-main rounded px-2 py-1.5">
              <Search className="w-3 h-3 text-zinc-500 shrink-0" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  if (!e.target.value.trim()) setSearchResults(null)
                }}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search files..."
                className="bg-transparent border-none outline-none flex-1 text-xs text-zinc-300 placeholder-zinc-600"
              />
            </div>
          </div>

          {/* File tree */}
          <div className="flex-1 overflow-y-auto p-4">
            <div className="space-y-1">
              {searchResults !== null ? (
                <>
                  <p className="text-[10px] text-zinc-600 mb-2">
                    {searchResults.length} result{searchResults.length !== 1 ? 's' : ''} for "{searchQuery}"
                    <span
                      className="ml-2 text-zinc-500 hover:text-zinc-300 cursor-pointer"
                      onClick={() => { setSearchResults(null); setSearchQuery('') }}
                    >
                      Clear
                    </span>
                  </p>
                  {searchResults.map((entry) => (
                    <div
                      key={entry.path}
                      onClick={() => {
                        if (entry.is_dir) {
                          setFilePath(entry.path)
                          setSearchResults(null)
                          setSearchQuery('')
                        } else {
                          handleDownload(entry.path)
                        }
                      }}
                      className="flex items-center gap-2 p-2 rounded hover:bg-zinc-900 cursor-pointer group"
                    >
                      {entry.is_dir ? (
                        <Folder className="w-4 h-4 text-zinc-500" />
                      ) : (
                        <FileText className="w-4 h-4 text-emerald-900" />
                      )}
                      <span className="text-xs text-zinc-400 group-hover:text-zinc-200 transition-colors truncate">
                        {entry.path}
                      </span>
                      {!entry.is_dir && (
                        <Download className="w-3 h-3 text-zinc-600 group-hover:text-emerald-500 ml-auto shrink-0" />
                      )}
                    </div>
                  ))}
                </>
              ) : (
                <>
                  {filePath !== '/' && (
                    <div
                      onClick={() => {
                        const parent = filePath.split('/').slice(0, -1).join('/') || '/'
                        setFilePath(parent)
                      }}
                      className="flex items-center gap-2 p-2 rounded hover:bg-zinc-900 cursor-pointer group"
                    >
                      <Folder className="w-4 h-4 text-zinc-500" />
                      <span className="text-xs text-zinc-400 group-hover:text-zinc-200 transition-colors italic">
                        ../
                      </span>
                    </div>
                  )}
                  {files.map((entry) => (
                    <div
                      key={entry.name}
                      onClick={() => {
                        if (entry.is_dir) {
                          setFilePath(entry.path)
                        } else {
                          handleDownload(entry.path)
                        }
                      }}
                      className={`flex items-center gap-2 p-2 rounded hover:bg-zinc-900 cursor-pointer group ${
                        !entry.is_dir ? 'pl-6' : ''
                      }`}
                    >
                      {entry.is_dir ? (
                        <Folder className="w-4 h-4 text-zinc-500" />
                      ) : (
                        <FileText className="w-4 h-4 text-emerald-900" />
                      )}
                      <span className="text-xs text-zinc-400 group-hover:text-zinc-200 transition-colors italic">
                        {entry.name}
                        {entry.is_dir ? '/' : ''}
                      </span>
                      {!entry.is_dir && entry.size && (
                        <span className="ml-auto text-[9px] mono text-zinc-700">
                          {formatSize(entry.size)}
                        </span>
                      )}
                      {!entry.is_dir && (
                        <Download className="w-3 h-3 text-zinc-600 group-hover:text-emerald-500 shrink-0" />
                      )}
                    </div>
                  ))}
                  {files.length === 0 && (
                    <p className="text-xs text-zinc-700 p-2">
                      {activeDevice ? 'No files found' : 'Connect a device to browse files'}
                    </p>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Command presets */}
          <div className="p-4 border-t border-main bg-black">
            <p className="text-[10px] font-bold text-zinc-600 uppercase mb-4 tracking-tighter">
              Command Presets
            </p>
            <div className="grid grid-cols-2 gap-2">
              {presets.map((p) => (
                <button
                  key={p.label}
                  onClick={() => setShellInput(p.cmd)}
                  className="text-[9px] font-bold bg-zinc-900 border border-main p-2 rounded text-zinc-400 hover:text-white hover:border-zinc-500"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="h-10 border-t border-main bg-zinc-950 flex items-center px-6 gap-6 shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
          <span className="text-[10px] mono text-emerald-500 font-bold">
            ADB STREAMING
          </span>
        </div>
        <div className="text-[10px] mono text-zinc-600 overflow-hidden whitespace-nowrap italic">
          [01-27 22:42:01.302] D/ActivityManager: User 0 state changed from
          RUNNING_LOCKED to RUNNING...
        </div>
      </footer>
    </>
  )
}

function formatSize(sizeStr) {
  const bytes = parseInt(sizeStr, 10)
  if (isNaN(bytes)) return sizeStr
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
