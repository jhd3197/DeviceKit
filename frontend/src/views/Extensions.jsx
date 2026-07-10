import React, { useState, useEffect, useCallback } from 'react'
import {
  Puzzle,
  Package,
  Search,
  X,
  Download,
  Trash2,
  Settings2,
  RefreshCw,
  Power,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  UploadCloud,
  Link2,
  Zap,
  Activity,
  Plug,
  Bot,
  Wrench,
} from 'lucide-react'
import { api } from '../api'
import { refreshContributions } from '../extensions/contributions'
import ExtensionIcon from '../extensions/ExtensionIcon'

// Marketplace / extension manager (plan 04), modeled on ServerKit's Marketplace.jsx but
// Tailwind-styled to DeviceKit's dark theme. Two tabs: Browse (builtin + registry catalog
// with a consent-gated install flow) and Installed (enable/disable, schema-driven config,
// keep-vs-purge uninstall). Any mutation re-fetches the contribution envelope so contributed
// nav/routes/widgets update live.

const CATEGORY_GLYPH = {
  automation: Zap,
  monitoring: Activity,
  integration: Plug,
  ai: Bot,
  utility: Wrench,
}

// Human-readable consent copy for each declared permission (matches the backend's
// KNOWN_PERMISSIONS). Shown as consent chips before install.
const PERMISSION_INFO = {
  adb: 'Run ADB commands on devices',
  'device.control': 'Tap, swipe, and input on devices',
  filesystem: 'Read and write device files',
  network: 'Make outbound network requests',
  llm: 'Call the AI provider (Prompture)',
}

const STATUS_STYLE = {
  active: { label: 'Active', cls: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' },
  disabled: { label: 'Disabled', cls: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/20' },
  error: { label: 'Error', cls: 'text-red-400 bg-red-500/10 border-red-500/20' },
}

function CategoryGlyph({ category, className = 'w-5 h-5' }) {
  const G = CATEGORY_GLYPH[category] || Puzzle
  return <G className={className} />
}

function PermissionChip({ perm }) {
  return (
    <span
      title={PERMISSION_INFO[perm] || perm}
      className="inline-flex items-center gap-1 text-[10px] mono px-2 py-0.5 rounded border border-amber-500/20 bg-amber-500/10 text-amber-300"
    >
      <ShieldCheck className="w-3 h-3" />
      {perm}
    </span>
  )
}

/** Cover-art fallback chain: registry logo → manifest SVG icon → category glyph. */
function CoverArt({ entry }) {
  if (entry.logo) {
    return (
      <img
        src={entry.logo}
        alt=""
        className="w-full h-full object-contain"
        onError={(e) => {
          e.currentTarget.style.display = 'none'
        }}
      />
    )
  }
  const iconSvg = entry.manifest?.contributions?.nav?.[0]?.icon
  if (iconSvg) return <ExtensionIcon svg={iconSvg} className="w-6 h-6 text-zinc-300" />
  return <CategoryGlyph category={entry.category} className="w-6 h-6 text-zinc-500" />
}

export default function Extensions() {
  const [tab, setTab] = useState('browse')
  const [catalog, setCatalog] = useState([])
  const [installed, setInstalled] = useState([])
  const [updates, setUpdates] = useState({})
  const [source, setSource] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState(null)

  const [filterText, setFilterText] = useState('')
  const [filterCat, setFilterCat] = useState('all')
  const [filterPerm, setFilterPerm] = useState('all')

  const [detail, setDetail] = useState(null) // registry entry open in the consent modal
  const [urlDialog, setUrlDialog] = useState(false)
  const [configFor, setConfigFor] = useState(null) // installed ext being configured
  const [uninstallFor, setUninstallFor] = useState(null)

  const showToast = (text, ok = true) => {
    setToast({ text, ok })
    setTimeout(() => setToast(null), 3500)
  }

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [reg, inst, upd] = await Promise.all([
        api.getExtensionRegistry().catch(() => ({ extensions: [], source: null })),
        api.getExtensions().catch(() => ({ extensions: [] })),
        api.getExtensionUpdates().catch(() => ({ updates: [] })),
      ])
      setCatalog(reg.extensions || [])
      setSource(reg.source || null)
      setInstalled(inst.extensions || [])
      const um = {}
      for (const u of upd.updates || []) um[u.slug] = u
      setUpdates(um)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  // Re-fetch local state + the live contribution envelope after any mutation.
  const afterMutation = useCallback(async () => {
    await loadAll()
    await refreshContributions()
  }, [loadAll])

  const doInstall = async (body, label) => {
    setBusy(true)
    try {
      await api.installExtension(body)
      showToast(`Installed ${label}.`)
      setDetail(null)
      setUrlDialog(false)
      await afterMutation()
    } catch (e) {
      showToast(e.message, false)
    } finally {
      setBusy(false)
    }
  }

  const doUpload = async (file) => {
    setBusy(true)
    try {
      const ext = await api.installExtensionUpload(file, true)
      showToast(`Installed ${ext.display_name || ext.slug}.`)
      await afterMutation()
    } catch (e) {
      showToast(e.message, false)
    } finally {
      setBusy(false)
    }
  }

  const toggleEnabled = async (ext) => {
    setBusy(true)
    try {
      if (ext.status === 'active') await api.disableExtension(ext.slug)
      else await api.enableExtension(ext.slug)
      await afterMutation()
    } catch (e) {
      showToast(e.message, false)
    } finally {
      setBusy(false)
    }
  }

  const doUpdate = async (slug) => {
    setBusy(true)
    try {
      await api.updateExtension(slug)
      showToast(`Updated ${slug}.`)
      await afterMutation()
    } catch (e) {
      showToast(e.message, false)
    } finally {
      setBusy(false)
    }
  }

  const doUninstall = async (slug, purge) => {
    setBusy(true)
    try {
      await api.uninstallExtension(slug, purge)
      showToast(`Uninstalled ${slug}${purge ? ' (data purged)' : ''}.`)
      setUninstallFor(null)
      await afterMutation()
    } catch (e) {
      showToast(e.message, false)
    } finally {
      setBusy(false)
    }
  }

  const categories = ['all', ...new Set(catalog.map((e) => e.category).filter(Boolean))]
  const allPerms = ['all', ...new Set(catalog.flatMap((e) => e.permissions || []))]

  const filtered = catalog.filter((e) => {
    if (filterCat !== 'all' && e.category !== filterCat) return false
    if (filterPerm !== 'all' && !(e.permissions || []).includes(filterPerm)) return false
    if (filterText) {
      const t = filterText.toLowerCase()
      if (
        !(e.display_name || '').toLowerCase().includes(t) &&
        !(e.description || '').toLowerCase().includes(t) &&
        !(e.slug || '').toLowerCase().includes(t)
      )
        return false
    }
    return true
  })

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-14 border-b border-main flex items-center justify-between px-8 bg-black/50 backdrop-blur-md shrink-0">
        <div className="flex items-center gap-2 text-sm font-semibold text-zinc-200">
          <Puzzle className="w-4 h-4 text-zinc-400" />
          Extensions
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setUrlDialog(true)}
            className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded border border-main text-zinc-300 hover:bg-zinc-900 transition-colors"
          >
            <Link2 className="w-3.5 h-3.5" /> From URL
          </button>
          <label className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded border border-main text-zinc-300 hover:bg-zinc-900 transition-colors cursor-pointer">
            <UploadCloud className="w-3.5 h-3.5" /> Upload
            <input
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.[0]) doUpload(e.target.files[0])
                e.target.value = ''
              }}
            />
          </label>
          <button
            onClick={loadAll}
            className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded border border-main text-zinc-300 hover:bg-zinc-900 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b border-main px-8 flex items-center gap-1 bg-black/30">
        {[
          ['browse', 'Browse', Package],
          ['installed', `Installed (${installed.length})`, Puzzle],
        ].map(([id, label, Icon]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-3 py-2.5 text-xs font-semibold border-b-2 -mb-px transition-colors ${
              tab === id
                ? 'border-white text-white'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-8">
        {loading ? (
          <div className="text-zinc-500 text-sm">Loading extensions…</div>
        ) : error ? (
          <div className="bg-red-950/50 border border-red-900/50 rounded-lg p-3 text-xs text-red-400">
            {error}
          </div>
        ) : tab === 'browse' ? (
          <BrowseTab
            filtered={filtered}
            source={source}
            categories={categories}
            allPerms={allPerms}
            filterText={filterText}
            setFilterText={setFilterText}
            filterCat={filterCat}
            setFilterCat={setFilterCat}
            filterPerm={filterPerm}
            setFilterPerm={setFilterPerm}
            onOpen={setDetail}
          />
        ) : (
          <InstalledTab
            installed={installed}
            updates={updates}
            busy={busy}
            onToggle={toggleEnabled}
            onUpdate={doUpdate}
            onConfigure={setConfigFor}
            onUninstall={setUninstallFor}
          />
        )}
      </div>

      {detail && (
        <DetailModal
          entry={detail}
          busy={busy}
          onClose={() => setDetail(null)}
          onInstall={() => doInstall({ slug: detail.slug }, detail.display_name || detail.slug)}
        />
      )}
      {urlDialog && (
        <UrlInstallDialog
          busy={busy}
          onClose={() => setUrlDialog(false)}
          onInstall={doInstall}
        />
      )}
      {configFor && (
        <ConfigModal
          ext={configFor}
          onClose={() => setConfigFor(null)}
          onSaved={() => {
            setConfigFor(null)
            showToast('Configuration saved.')
            loadAll()
          }}
        />
      )}
      {uninstallFor && (
        <UninstallDialog
          ext={uninstallFor}
          busy={busy}
          onClose={() => setUninstallFor(null)}
          onConfirm={(purge) => doUninstall(uninstallFor.slug, purge)}
        />
      )}

      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-lg border text-xs font-medium shadow-lg ${
            toast.ok
              ? 'bg-emerald-950/90 border-emerald-800 text-emerald-300'
              : 'bg-red-950/90 border-red-800 text-red-300'
          }`}
        >
          {toast.ok ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
          {toast.text}
        </div>
      )}
    </div>
  )
}

function BrowseTab({
  filtered,
  source,
  categories,
  allPerms,
  filterText,
  setFilterText,
  filterCat,
  setFilterCat,
  filterPerm,
  setFilterPerm,
  onOpen,
}) {
  return (
    <div className="space-y-5 max-w-7xl">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-zinc-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Search extensions…"
            className="w-full bg-card border border-main rounded pl-9 pr-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-border-alt"
          />
        </div>
        <select
          value={filterCat}
          onChange={(e) => setFilterCat(e.target.value)}
          className="bg-card border border-main rounded px-3 py-2 text-xs text-zinc-300 focus:outline-none"
        >
          {categories.map((c) => (
            <option key={c} value={c}>
              {c === 'all' ? 'All categories' : c}
            </option>
          ))}
        </select>
        <select
          value={filterPerm}
          onChange={(e) => setFilterPerm(e.target.value)}
          className="bg-card border border-main rounded px-3 py-2 text-xs text-zinc-300 focus:outline-none"
        >
          {allPerms.map((p) => (
            <option key={p} value={p}>
              {p === 'all' ? 'All permissions' : p}
            </option>
          ))}
        </select>
        {source && (
          <span className="text-[10px] mono uppercase tracking-widest text-zinc-600">
            registry: {source}
          </span>
        )}
      </div>

      {filtered.length === 0 ? (
        <div className="bg-card border border-main rounded-lg p-8 text-center text-zinc-500 text-sm">
          No extensions match your filters.
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((e) => (
            <button
              key={e.slug}
              onClick={() => onOpen(e)}
              className="text-left bg-card border border-main rounded-lg p-4 hover:border-border-alt transition-colors group"
            >
              <div className="flex items-start gap-3">
                <div className="w-11 h-11 rounded bg-zinc-900 border border-main flex items-center justify-center shrink-0 overflow-hidden">
                  <CoverArt entry={e} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-zinc-200 truncate">
                      {e.display_name || e.slug}
                    </p>
                    {e.first_party && (
                      <span className="text-[9px] mono uppercase text-blue-400 bg-blue-500/10 border border-blue-500/20 rounded px-1">
                        1st party
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] mono text-zinc-500">
                    v{e.version} · {e.category}
                  </p>
                </div>
                {e.installed && (
                  <span className="text-[9px] mono uppercase text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-1.5 py-0.5 shrink-0">
                    Installed
                  </span>
                )}
              </div>
              <p className="mt-3 text-xs text-zinc-400 line-clamp-2">{e.description}</p>
              {(e.permissions || []).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {e.permissions.map((p) => (
                    <PermissionChip key={p} perm={p} />
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function DetailModal({ entry, busy, onClose, onInstall }) {
  const compatWarn = entry.min_devicekit_version
    ? `Requires DeviceKit ${entry.min_devicekit_version}${
        entry.max_devicekit_version ? `–${entry.max_devicekit_version}` : '+'
      }`
    : null

  return (
    <Modal onClose={onClose} wide>
      <div className="flex items-start gap-4">
        <div className="w-14 h-14 rounded bg-zinc-900 border border-main flex items-center justify-center shrink-0 overflow-hidden">
          <CoverArt entry={entry} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-zinc-100">{entry.display_name || entry.slug}</h2>
            {entry.first_party && (
              <span className="text-[9px] mono uppercase text-blue-400 bg-blue-500/10 border border-blue-500/20 rounded px-1">
                1st party
              </span>
            )}
          </div>
          <p className="text-[10px] mono text-zinc-500">
            {entry.slug} · v{entry.version} · {entry.category}
            {entry.author ? ` · ${entry.author}` : ''}
          </p>
        </div>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
          <X className="w-5 h-5" />
        </button>
      </div>

      <p className="mt-4 text-sm text-zinc-300">{entry.description}</p>

      {(entry.screenshots || []).length > 0 && (
        <div className="mt-4 flex gap-3 overflow-x-auto pb-1">
          {entry.screenshots.map((s, i) => (
            <img
              key={i}
              src={s}
              alt=""
              className="h-40 rounded border border-main shrink-0"
              onError={(e) => {
                e.currentTarget.style.display = 'none'
              }}
            />
          ))}
        </div>
      )}

      {/* Consent chips */}
      <div className="mt-5">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500 mb-2">
          Requested permissions
        </p>
        {(entry.permissions || []).length === 0 ? (
          <p className="text-xs text-zinc-500">No special permissions requested.</p>
        ) : (
          <div className="space-y-1.5">
            {entry.permissions.map((p) => (
              <div key={p} className="flex items-center gap-2 text-xs text-zinc-300">
                <ShieldCheck className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <span className="mono text-amber-300">{p}</span>
                <span className="text-zinc-500">— {PERMISSION_INFO[p] || 'custom capability'}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {compatWarn && (
        <p className="mt-4 text-[11px] text-zinc-500 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5" /> {compatWarn}
        </p>
      )}

      <div className="mt-6 flex items-center justify-end gap-2">
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-xs font-medium rounded border border-main text-zinc-300 hover:bg-zinc-900"
        >
          Cancel
        </button>
        {entry.installed ? (
          <span className="px-3 py-1.5 text-xs font-semibold rounded bg-zinc-800 text-zinc-400 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" /> Installed (v{entry.installed_version})
          </span>
        ) : (
          <button
            onClick={onInstall}
            disabled={busy}
            className="px-3 py-1.5 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" /> {busy ? 'Installing…' : 'Install & grant'}
          </button>
        )}
      </div>
    </Modal>
  )
}

function UrlInstallDialog({ busy, onClose, onInstall }) {
  const [url, setUrl] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [err, setErr] = useState(null)

  const doPreview = async () => {
    setPreviewing(true)
    setErr(null)
    try {
      const p = await api.previewExtension({ url })
      setPreview(p)
    } catch (e) {
      setErr(e.message)
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <Modal onClose={onClose}>
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold text-zinc-100">Install from URL</h2>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
          <X className="w-5 h-5" />
        </button>
      </div>
      <p className="mt-2 text-xs text-zinc-500">
        Paste a zip URL. We resolve its manifest and checksum first so you can review the
        requested permissions before granting.
      </p>
      <div className="mt-4 flex gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://…/extension.zip"
          className="flex-1 bg-black border border-main rounded px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-border-alt"
        />
        <button
          onClick={doPreview}
          disabled={!url || previewing}
          className="px-3 py-2 text-xs font-semibold rounded border border-main text-zinc-300 hover:bg-zinc-900 disabled:opacity-50"
        >
          {previewing ? 'Resolving…' : 'Preview'}
        </button>
      </div>

      {err && <p className="mt-3 text-xs text-red-400">{err}</p>}

      {preview && (
        <div className="mt-4 bg-card border border-main rounded-lg p-4 space-y-3">
          <div>
            <p className="text-sm font-semibold text-zinc-200">
              {preview.display_name} <span className="text-zinc-500 mono">v{preview.version}</span>
            </p>
            <p className="text-xs text-zinc-400 mt-0.5">{preview.description}</p>
          </div>
          {(preview.permissions || []).length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500 mb-1.5">
                Requested permissions
              </p>
              <div className="flex flex-wrap gap-1.5">
                {preview.permissions.map((p) => (
                  <PermissionChip key={p} perm={p} />
                ))}
              </div>
            </div>
          )}
          <p className="text-[10px] mono text-zinc-600 break-all">sha256: {preview.sha256}</p>
          {(preview.warnings || []).map((w, i) => (
            <p key={i} className="text-[11px] text-amber-400 flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {w}
            </p>
          ))}
          <div className="flex justify-end">
            <button
              onClick={() =>
                onInstall(
                  { url, sha256: preview.sha256, force: true },
                  preview.display_name || preview.slug
                )
              }
              disabled={busy}
              className="px-3 py-1.5 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white flex items-center gap-1.5"
            >
              <Download className="w-3.5 h-3.5" /> {busy ? 'Installing…' : 'Install & grant'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function InstalledTab({ installed, updates, busy, onToggle, onUpdate, onConfigure, onUninstall }) {
  if (installed.length === 0) {
    return (
      <div className="bg-card border border-main rounded-lg p-8 text-center text-zinc-500 text-sm max-w-3xl">
        No extensions installed yet. Head to <span className="text-zinc-300">Browse</span> to
        install one.
      </div>
    )
  }
  return (
    <div className="space-y-3 max-w-4xl">
      {installed.map((ext) => {
        const st = STATUS_STYLE[ext.status] || STATUS_STYLE.disabled
        const upd = updates[ext.slug]
        const hasConfig = Object.keys(ext.manifest?.config_schema || {}).length > 0
        return (
          <div
            key={ext.slug}
            className="bg-card border border-main rounded-lg p-4 flex items-center gap-4"
          >
            <div className="w-10 h-10 rounded bg-zinc-900 border border-main flex items-center justify-center shrink-0">
              <CategoryGlyph category={ext.category} className="w-5 h-5 text-zinc-400" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-zinc-200">{ext.display_name}</p>
                <span className={`text-[9px] mono uppercase px-1.5 py-0.5 rounded border ${st.cls}`}>
                  {st.label}
                </span>
                {upd?.has_update && (
                  <span className="text-[9px] mono uppercase px-1.5 py-0.5 rounded border border-blue-500/20 bg-blue-500/10 text-blue-400">
                    update → v{upd.available_version}
                  </span>
                )}
              </div>
              <p className="text-[10px] mono text-zinc-500 mt-0.5">
                {ext.slug} · v{ext.version} · {ext.source || 'local'}
              </p>
              {ext.status === 'error' && ext.error && (
                <p className="text-[10px] text-red-400 mt-1 line-clamp-2">{ext.error}</p>
              )}
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {upd?.has_update && (
                <button
                  onClick={() => onUpdate(ext.slug)}
                  disabled={busy}
                  title="Update"
                  className="p-1.5 rounded border border-main text-blue-400 hover:bg-zinc-900 disabled:opacity-50"
                >
                  <Download className="w-4 h-4" />
                </button>
              )}
              {hasConfig && (
                <button
                  onClick={() => onConfigure(ext)}
                  title="Configure"
                  className="p-1.5 rounded border border-main text-zinc-300 hover:bg-zinc-900"
                >
                  <Settings2 className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={() => onToggle(ext)}
                disabled={busy || ext.status === 'error'}
                title={ext.status === 'active' ? 'Disable' : 'Enable'}
                className={`p-1.5 rounded border border-main hover:bg-zinc-900 disabled:opacity-40 ${
                  ext.status === 'active' ? 'text-emerald-400' : 'text-zinc-500'
                }`}
              >
                <Power className="w-4 h-4" />
              </button>
              <button
                onClick={() => onUninstall(ext)}
                title="Uninstall"
                className="p-1.5 rounded border border-main text-red-400 hover:bg-red-950/40"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ConfigModal({ ext, onClose, onSaved }) {
  const schema = ext.manifest?.config_schema || {}
  const [values, setValues] = useState({})
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api
      .getExtensionConfig(ext.slug)
      .then((r) => setValues(r.config || {}))
      .catch(() => setValues({}))
      .finally(() => setLoaded(true))
  }, [ext.slug])

  const setField = (key, val) => setValues((v) => ({ ...v, [key]: val }))

  const save = async () => {
    setSaving(true)
    setErr(null)
    try {
      // Don't overwrite a secret the user left as the masked placeholder.
      const payload = {}
      for (const [key, spec] of Object.entries(schema)) {
        const val = values[key]
        if (spec.secret && val === '••••••') continue
        if (val !== undefined) payload[key] = val
      }
      await api.updateExtensionConfig(ext.slug, payload)
      onSaved()
    } catch (e) {
      setErr(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal onClose={onClose}>
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold text-zinc-100">Configure {ext.display_name}</h2>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
          <X className="w-5 h-5" />
        </button>
      </div>

      {!loaded ? (
        <p className="mt-4 text-sm text-zinc-500">Loading…</p>
      ) : Object.keys(schema).length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">This extension has no configurable settings.</p>
      ) : (
        <div className="mt-4 space-y-4">
          {Object.entries(schema).map(([key, spec]) => (
            <ConfigField
              key={key}
              name={key}
              spec={spec}
              value={values[key]}
              onChange={(v) => setField(key, v)}
            />
          ))}
        </div>
      )}

      {err && <p className="mt-3 text-xs text-red-400">{err}</p>}

      <div className="mt-6 flex justify-end gap-2">
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-xs font-medium rounded border border-main text-zinc-300 hover:bg-zinc-900"
        >
          Cancel
        </button>
        <button
          onClick={save}
          disabled={saving}
          className="px-3 py-1.5 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </Modal>
  )
}

function ConfigField({ name, spec, value, onChange }) {
  const label = spec.label || name
  const type = spec.secret ? 'secret' : spec.type || 'string'

  if (type === 'boolean') {
    return (
      <label className="flex items-center gap-2.5 cursor-pointer">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
          className="w-4 h-4 accent-emerald-500"
        />
        <span className="text-sm text-zinc-300">{label}</span>
      </label>
    )
  }

  if (type === 'enum' && Array.isArray(spec.options)) {
    return (
      <div>
        <label className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500 mb-1.5 block">
          {label}
        </label>
        <select
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
          className="w-full bg-black border border-main rounded px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-border-alt"
        >
          <option value="">— select —</option>
          {spec.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>
    )
  }

  return (
    <div>
      <label className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500 mb-1.5 block">
        {label}
        {spec.secret && <span className="ml-1.5 text-amber-500 normal-case">(secret)</span>}
      </label>
      <input
        type={type === 'number' ? 'number' : spec.secret ? 'password' : 'text'}
        value={value ?? ''}
        onChange={(e) => onChange(type === 'number' ? Number(e.target.value) : e.target.value)}
        placeholder={spec.secret ? '••••••' : ''}
        className="w-full bg-black border border-main rounded px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-border-alt"
      />
    </div>
  )
}

function UninstallDialog({ ext, busy, onClose, onConfirm }) {
  const [purge, setPurge] = useState(false)
  return (
    <Modal onClose={onClose}>
      <div className="flex items-center gap-2 text-red-400">
        <AlertTriangle className="w-5 h-5" />
        <h2 className="text-base font-bold">Uninstall {ext.display_name}?</h2>
      </div>
      <p className="mt-3 text-sm text-zinc-400">
        This removes the extension's routes, nav, widgets, and contributed step types / fields.
      </p>
      <label className="mt-4 flex items-start gap-2.5 cursor-pointer bg-card border border-main rounded-lg p-3">
        <input
          type="checkbox"
          checked={purge}
          onChange={(e) => setPurge(e.target.checked)}
          className="w-4 h-4 mt-0.5 accent-red-500"
        />
        <span className="text-sm text-zinc-300">
          Purge data
          <span className="block text-xs text-zinc-500 mt-0.5">
            Also drop this extension's <span className="mono">ext_{ext.slug.replace(/-/g, '_')}_*</span>{' '}
            tables. Leave unchecked to keep data for a future reinstall.
          </span>
        </span>
      </label>
      <div className="mt-6 flex justify-end gap-2">
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-xs font-medium rounded border border-main text-zinc-300 hover:bg-zinc-900"
        >
          Cancel
        </button>
        <button
          onClick={() => onConfirm(purge)}
          disabled={busy}
          className="px-3 py-1.5 text-xs font-semibold rounded bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white flex items-center gap-1.5"
        >
          <Trash2 className="w-3.5 h-3.5" />
          {busy ? 'Uninstalling…' : purge ? 'Uninstall & purge' : 'Uninstall'}
        </button>
      </div>
    </Modal>
  )
}

function Modal({ children, onClose, wide }) {
  return (
    <div
      className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className={`bg-black border border-main rounded-xl p-6 w-full ${
          wide ? 'max-w-2xl' : 'max-w-lg'
        } max-h-[85vh] overflow-y-auto shadow-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}
