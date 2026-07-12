// File Explorer — builtin extension frontend (plan 15).
//
// SOURCE OF TRUTH. Synced verbatim into frontend/src/extensions/devicekit-explorer/index.jsx
// by scripts/sync-builtin-frontends.mjs (CI enforces no drift). Do not edit the copy.
//
// The first builtin frontend beyond a settings panel: a full page (ExplorerPage) AND a
// NodeDetail tab (FilesTab), both sharing one FileBrowser. Imports host code ONLY from the
// stable `devicekit-sdk` alias.
import React, { useEffect, useState, useRef, useCallback } from 'react'
import { api } from 'devicekit-sdk'

export const contributions = {
  nav: [{ id: 'explorer', label: 'File Explorer', route: '/x/explorer', section: 'Extensions' }],
  routes: [{ path: '/x/explorer', component: 'ExplorerPage' }],
  widgets: [{ slot: 'node-detail.tabs', component: 'FilesTab' }],
  page_titles: { '/x/explorer': 'File Explorer' },
}

const IMAGE_EXT = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg']

function fmtSize(n) {
  if (n == null) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function fmtTime(ms) {
  if (!ms) return ''
  try {
    return new Date(ms).toLocaleString()
  } catch {
    return ''
  }
}

function parentOf(path) {
  if (!path || path === '/') return '/'
  const trimmed = path.replace(/\/+$/, '')
  const idx = trimmed.lastIndexOf('/')
  return idx <= 0 ? '/' : trimmed.slice(0, idx)
}

function join(dir, name) {
  return `${dir.replace(/\/+$/, '')}/${name}`
}

function ext(name) {
  const i = (name || '').lastIndexOf('.')
  return i < 0 ? '' : name.slice(i + 1).toLowerCase()
}

/** The reusable file browser. `deviceId` selects the device; everything else is self-contained. */
export function FileBrowser({ deviceId }) {
  const [path, setPath] = useState('/sdcard')
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [preview, setPreview] = useState(null) // { name, url, isImage, text }
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef(null)

  const load = useCallback(
    (p) => {
      if (!deviceId) return
      setLoading(true)
      setError(null)
      api
        .explorerList(deviceId, p)
        .then((r) => setEntries(r.entries || []))
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false))
    },
    [deviceId]
  )

  useEffect(() => {
    load(path)
  }, [path, load])

  const crumbs = path.split('/').filter(Boolean)

  const openEntry = (e) => {
    if (e.is_dir) {
      setPath(e.path)
    } else if (IMAGE_EXT.includes(ext(e.name))) {
      setPreview({ name: e.name, url: api.explorerPreviewUrl(deviceId, e.path), isImage: true })
    } else {
      fetch(api.explorerPreviewUrl(deviceId, e.path), {
        headers: { 'X-API-Key': localStorage.getItem('devicekit_api_key') || '' },
      })
        .then((r) => r.text())
        .then((text) => setPreview({ name: e.name, text: text.slice(0, 20000), isImage: false }))
        .catch(() => setPreview({ name: e.name, text: '(could not preview)', isImage: false }))
    }
  }

  const doMkdir = async () => {
    const name = window.prompt('New folder name:')
    if (!name) return
    try {
      await api.explorerMkdir(deviceId, join(path, name))
      load(path)
    } catch (e) {
      alert(`mkdir failed: ${e.message}`)
    }
  }

  const doRename = async (e) => {
    const name = window.prompt('Rename to:', e.name)
    if (!name || name === e.name) return
    try {
      await api.explorerRename(deviceId, e.path, join(parentOf(e.path), name))
      load(path)
    } catch (err) {
      alert(`rename failed: ${err.message}`)
    }
  }

  const doDelete = async (e) => {
    if (!window.confirm(`Delete ${e.is_dir ? 'folder' : 'file'} "${e.name}"? This cannot be undone.`)) return
    try {
      await api.explorerDelete(deviceId, e.path)
      load(path)
    } catch (err) {
      alert(`delete failed: ${err.message}`)
    }
  }

  const doUpload = async (files) => {
    for (const f of files) {
      try {
        await api.uploadFile(deviceId, f, path)
      } catch (e) {
        alert(`upload failed for ${f.name}: ${e.message}`)
      }
    }
    load(path)
  }

  const onDrop = (ev) => {
    ev.preventDefault()
    setDragging(false)
    if (ev.dataTransfer?.files?.length) doUpload([...ev.dataTransfer.files])
  }

  if (!deviceId) return <div className="text-sm text-zinc-500 p-4">No device selected.</div>

  return (
    <div className="flex flex-col">
      {/* Toolbar + breadcrumb */}
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <button
          onClick={() => setPath(parentOf(path))}
          disabled={path === '/'}
          className="px-2 py-1 text-xs rounded border border-main text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
        >
          ↑ Up
        </button>
        <div className="flex items-center gap-1 text-xs text-zinc-400 mono flex-1 min-w-0 overflow-x-auto">
          <button className="hover:text-emerald-400" onClick={() => setPath('/')}>/</button>
          {crumbs.map((c, i) => {
            const p = '/' + crumbs.slice(0, i + 1).join('/')
            return (
              <span key={p} className="flex items-center gap-1">
                <button className="hover:text-emerald-400 truncate max-w-[10rem]" onClick={() => setPath(p)}>
                  {c}
                </button>
                <span className="text-zinc-600">/</span>
              </span>
            )
          })}
        </div>
        <button onClick={() => load(path)} className="px-2 py-1 text-xs rounded border border-main text-zinc-300 hover:bg-zinc-800">
          Refresh
        </button>
        <button onClick={doMkdir} className="px-2 py-1 text-xs rounded border border-main text-zinc-300 hover:bg-zinc-800">
          New Folder
        </button>
        <button
          onClick={() => fileInput.current?.click()}
          className="px-2 py-1 text-xs rounded bg-emerald-600 hover:bg-emerald-500 text-white"
        >
          Upload
        </button>
        <input
          ref={fileInput}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => e.target.files?.length && doUpload([...e.target.files])}
        />
      </div>

      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}

      {/* Table (drag-drop target) */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`bg-card border rounded-lg overflow-hidden ${dragging ? 'border-emerald-500' : 'border-main'}`}
      >
        <table className="w-full text-left border-collapse">
          <thead className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest bg-zinc-900/20">
            <tr>
              <th className="p-3 border-b border-main">Name</th>
              <th className="p-3 border-b border-main w-28">Size</th>
              <th className="p-3 border-b border-main w-48">Modified</th>
              <th className="p-3 border-b border-main w-40 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="text-sm">
            {loading && (
              <tr>
                <td colSpan={4} className="p-6 text-center text-zinc-600 text-xs">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && entries.length === 0 && (
              <tr>
                <td colSpan={4} className="p-6 text-center text-zinc-600 text-xs">
                  Empty folder{dragging ? ' — drop to upload' : ''}
                </td>
              </tr>
            )}
            {!loading &&
              entries.map((e) => (
                <tr key={e.path} className="hover:bg-zinc-900/50 transition-colors group">
                  <td className="p-3 border-b border-main">
                    <button className="flex items-center gap-2 text-left" onClick={() => openEntry(e)}>
                      <span className={e.is_dir ? 'text-amber-400' : 'text-zinc-500'}>{e.is_dir ? '📁' : '📄'}</span>
                      <span className="text-zinc-200 group-hover:text-strong truncate max-w-[22rem]">{e.name}</span>
                    </button>
                  </td>
                  <td className="p-3 border-b border-main text-zinc-500 mono text-xs">
                    {e.is_dir ? '' : fmtSize(e.size)}
                  </td>
                  <td className="p-3 border-b border-main text-zinc-500 mono text-xs">{fmtTime(e.mtime)}</td>
                  <td className="p-3 border-b border-main text-right whitespace-nowrap">
                    {!e.is_dir && (
                      <a
                        href={api.downloadFileUrl(deviceId, e.path)}
                        className="text-[11px] text-blue-400 hover:text-blue-300 mr-3"
                      >
                        Download
                      </a>
                    )}
                    <button onClick={() => doRename(e)} className="text-[11px] text-zinc-400 hover:text-zinc-200 mr-3">
                      Rename
                    </button>
                    <button onClick={() => doDelete(e)} className="text-[11px] text-red-400 hover:text-red-300">
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Preview modal */}
      {preview && (
        <div
          className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-8"
          onClick={() => setPreview(null)}
        >
          <div
            className="bg-card border border-main rounded-lg max-w-3xl max-h-[85vh] overflow-auto p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-zinc-200 mono">{preview.name}</span>
              <button onClick={() => setPreview(null)} className="text-zinc-500 hover:text-zinc-200 text-lg">
                ✕
              </button>
            </div>
            {preview.isImage ? (
              <img src={preview.url} alt={preview.name} className="max-w-full rounded" />
            ) : (
              <pre className="text-xs text-zinc-300 whitespace-pre-wrap break-words">{preview.text}</pre>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/** NodeDetail tab — mounted into the `node-detail.tabs` slot; receives `deviceId` from the host. */
export function FilesTab({ deviceId }) {
  return (
    <div className="bg-card-alt border border-main rounded-xl">
      <div className="px-6 py-4 border-b border-main bg-zinc-900/20 flex items-center gap-3">
        <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Files</span>
        <span className="text-[10px] mono uppercase tracking-widest text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-2 py-0.5">
          Explorer
        </span>
      </div>
      <div className="p-6">
        <FileBrowser deviceId={deviceId} />
      </div>
    </div>
  )
}

/** Full page mounted at /x/explorer — pick a device, then browse its files. */
export function ExplorerPage() {
  const [devices, setDevices] = useState([])
  const [deviceId, setDeviceId] = useState('')

  useEffect(() => {
    api
      .getDevices()
      .then((r) => {
        const list = r.devices || []
        setDevices(list)
        if (list.length && !deviceId) setDeviceId(list[0].device_id)
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <header className="h-14 border-b border-main flex items-center px-8 bg-black/50 backdrop-blur-md shrink-0 gap-3">
        <span className="text-sm font-semibold text-zinc-200">File Explorer</span>
        <span className="text-[10px] mono uppercase tracking-widest text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-2 py-0.5">
          Extension
        </span>
        <div className="flex-1" />
        <select
          value={deviceId}
          onChange={(e) => setDeviceId(e.target.value)}
          className="bg-body border border-main rounded px-3 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-border-alt"
        >
          <option value="">Select a device…</option>
          {devices.map((d) => (
            <option key={d.device_id} value={d.device_id}>
              {d.model || d.device_id}
            </option>
          ))}
        </select>
      </header>

      <div className="flex-1 overflow-y-auto p-8">
        {deviceId ? (
          <FileBrowser deviceId={deviceId} />
        ) : (
          <p className="text-sm text-zinc-500">Select a device to browse its files.</p>
        )}
      </div>
    </div>
  )
}
