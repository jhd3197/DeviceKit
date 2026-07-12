// About pane (plan 12): version + build info for this DeviceKit instance.
import React, { useEffect, useState } from 'react'
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { Pane } from './fields'
import Logo from '../Logo'
import { api } from '../../api'

const APP_VERSION = '1.0.0' // mirrors frontend/package.json

function InfoRow({ label, children }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-main last:border-b-0">
      <span className="text-sm text-zinc-400">{label}</span>
      <span className="text-sm text-zinc-200 font-mono">{children}</span>
    </div>
  )
}

export default function About({ settings, register }) {
  const reg = register || (() => ({}))
  const [sdkVersion, setSdkVersion] = useState(null)
  const [health, setHealth] = useState('checking') // checking | ok | down

  useEffect(() => {
    let active = true
    api
      .getSdkVersion()
      .then((r) => active && setSdkVersion(r.sdk_version))
      .catch(() => active && setSdkVersion('unavailable'))
    api
      .getHealth?.()
      ?.then(() => active && setHealth('ok'))
      ?.catch(() => active && setHealth('down'))
    return () => {
      active = false
    }
  }, [])

  const instanceName = settings?.['general.instance_name'] || 'DeviceKit'

  return (
    <Pane title="About" description="Version and build details for this instance.">
      <div className="flex items-center gap-4 rounded-lg border border-main bg-card p-5">
        <Logo size={64} className="rounded-lg shrink-0" />
        <div>
          <p className="font-bold text-lg tracking-tight">{instanceName}</p>
          <p className="text-xs text-zinc-500">DeviceKit — Android fleet control plane</p>
        </div>
      </div>

      <div className="rounded-lg border border-main bg-card px-5" {...reg('about-version')}>
        <InfoRow label="App version">v{APP_VERSION}</InfoRow>
        <InfoRow label="Extension SDK">
          {sdkVersion == null ? <Loader2 className="w-4 h-4 animate-spin inline" /> : sdkVersion}
        </InfoRow>
        <InfoRow label="Backend">
          {health === 'checking' && <Loader2 className="w-4 h-4 animate-spin inline text-zinc-500" />}
          {health === 'ok' && (
            <span className="inline-flex items-center gap-1.5 text-emerald-400">
              <CheckCircle2 className="w-4 h-4" /> connected
            </span>
          )}
          {health === 'down' && (
            <span className="inline-flex items-center gap-1.5 text-red-400">
              <XCircle className="w-4 h-4" /> unreachable
            </span>
          )}
        </InfoRow>
      </div>

      <div className="rounded-md border border-main bg-card p-4 text-xs text-zinc-500 leading-relaxed">
        The Android agent APK is built and installed via the{' '}
        <span className="font-mono text-zinc-400">build-agent-apk</span> workflow. A registry URL
        and in-app APK download will appear here once the agent-distribution backend lands.
      </div>
    </Pane>
  )
}
