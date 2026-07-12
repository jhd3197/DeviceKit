// Security pane (plan 20): the CURRENT user's own account security. Shows who you are
// signed in as, self-service TOTP two-factor enrollment (setup → confirm → one-time
// backup codes) or disable, the require-2FA policy status, and sign out. 2FA only
// applies to real user accounts — solo/api-key principals have no user_id to enroll.
import React, { useState } from 'react'
import {
  ShieldCheck,
  ShieldOff,
  LogOut,
  Loader2,
  Copy,
  Check,
  KeyRound,
} from 'lucide-react'
import { Pane } from './fields'
import { api } from '../../api'
import { useAuth } from '../../auth/AuthContext'

export default function Security({ settings, save, register }) {
  const reg = register || (() => ({}))
  const { principal, twofa, logout, refresh } = useAuth()

  const [setup, setSetup] = useState(null) // { secret, provisioning_uri }
  const [code, setCode] = useState('')
  const [backupCodes, setBackupCodes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)
  const [signingOut, setSigningOut] = useState(false)

  const hasUser = !!principal?.user_id
  const enrolled = !!twofa?.enrolled

  const startSetup = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await api.setup2fa()
      setSetup(res)
      setCode('')
      setBackupCodes(null)
    } catch (e) {
      setError(e.message || 'Failed to start 2FA setup')
    } finally {
      setBusy(false)
    }
  }

  const confirm = async () => {
    const c = code.trim()
    if (!c || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.confirm2fa(c)
      setBackupCodes(res.backup_codes || [])
      setSetup(null)
      setCode('')
      await refresh()
    } catch (e) {
      setError(e.message || 'Invalid code — try again')
    } finally {
      setBusy(false)
    }
  }

  const disable = async () => {
    if (!window.confirm('Disable two-factor authentication for your account?')) return
    setBusy(true)
    setError(null)
    try {
      await api.disable2fa()
      setSetup(null)
      setBackupCodes(null)
      await refresh()
    } catch (e) {
      setError(e.message || 'Failed to disable 2FA')
    } finally {
      setBusy(false)
    }
  }

  const copySecret = async () => {
    if (!setup?.secret) return
    try {
      await navigator.clipboard.writeText(setup.secret)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }

  const signOut = async () => {
    setSigningOut(true)
    try {
      await logout()
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <Pane
      title="Security"
      description="Your own account security: two-factor authentication and session sign-out."
    >
      {/* Current account */}
      <div className="rounded-md border border-main bg-card px-4 py-3">
        <div className="text-sm text-zinc-200 font-medium">
          {principal?.username || 'Not signed in'}
        </div>
        {principal?.role && <div className="text-xs text-zinc-500 mt-0.5">Role: {principal.role}</div>}
      </div>

      {/* Require-2FA policy warning */}
      {twofa?.must_enroll && (
        <div className="rounded-md border border-main bg-card px-4 py-3 text-sm text-amber-400">
          Your account must enable two-factor authentication to keep full access.
        </div>
      )}

      {error && <div className="text-sm text-red-400">{error}</div>}

      {/* Two-factor authentication */}
      <div className="space-y-4" {...reg('two-factor-auth')}>
        <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
          {enrolled ? (
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          ) : (
            <ShieldOff className="w-4 h-4 text-zinc-500" />
          )}
          Two-factor authentication
          {enrolled && <span className="text-xs text-emerald-400">Enabled</span>}
        </div>

        {!hasUser ? (
          <div className="rounded-md border border-main bg-card p-4 text-xs text-zinc-500 leading-relaxed">
            2FA applies to real user accounts only. You are signed in as a solo or API-key
            principal, which has no user account to enroll.
          </div>
        ) : enrolled ? (
          <button
            type="button"
            onClick={disable}
            disabled={busy}
            className="flex items-center gap-1.5 border border-alt rounded-md px-3 py-1.5 text-sm text-red-400 hover:text-red-300 disabled:opacity-40"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldOff className="w-4 h-4" />}
            Disable 2FA
          </button>
        ) : setup ? (
          <div className="rounded-md border border-main bg-card p-4 space-y-4">
            <p className="text-xs text-zinc-500 leading-relaxed">
              Enter this secret in your authenticator app (or open the provisioning link on a
              device with one), then confirm with the 6-digit code it generates.
            </p>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <KeyRound className="w-4 h-4 text-zinc-600 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  readOnly
                  value={setup.secret || ''}
                  className="w-full bg-body border border-alt rounded-md pl-9 pr-3 py-2 text-sm text-zinc-200 font-mono focus:outline-none"
                />
              </div>
              <button
                type="button"
                onClick={copySecret}
                title="Copy secret"
                className="p-2 text-zinc-400 hover:text-strong border border-alt rounded-md"
              >
                {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
            {setup.provisioning_uri && (
              <div className="text-xs text-zinc-500 break-all">
                Provisioning URI:{' '}
                <a
                  href={setup.provisioning_uri}
                  className="font-mono text-zinc-400 hover:text-zinc-200 underline underline-offset-2"
                >
                  {setup.provisioning_uri}
                </a>
              </div>
            )}
            <div className="flex items-center gap-2">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') confirm()
                }}
                placeholder="6-digit code"
                className="w-36 bg-body border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 font-mono placeholder:text-zinc-600 focus:outline-none focus:border-accent"
              />
              <button
                type="button"
                onClick={confirm}
                disabled={busy || code.trim().length !== 6}
                className="flex items-center gap-1.5 bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors"
              >
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                Confirm
              </button>
              <button
                type="button"
                onClick={() => {
                  setSetup(null)
                  setCode('')
                }}
                className="text-sm text-zinc-400 hover:text-strong px-2 py-2"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={startSetup}
            disabled={busy}
            className="flex items-center gap-1.5 bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
            Set up 2FA
          </button>
        )}

        {/* One-time backup codes */}
        {backupCodes && (
          <div className="rounded-md border border-alt bg-hover p-4 space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-amber-400">
              <ShieldCheck className="w-4 h-4" /> Save these backup codes — they are shown only once.
            </div>
            <p className="text-xs text-zinc-500">
              Each code can be used once to sign in if you lose access to your authenticator.
            </p>
            <div className="grid grid-cols-2 gap-2">
              {backupCodes.map((c) => (
                <div
                  key={c}
                  className="bg-body border border-alt rounded-md px-3 py-2 text-sm font-mono text-zinc-200 text-center"
                >
                  {c}
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setBackupCodes(null)}
              className="border border-alt rounded-md px-3 py-1.5 text-sm text-zinc-400 hover:text-strong"
            >
              I saved them
            </button>
          </div>
        )}
      </div>

      {/* Sign out */}
      <div className="flex items-center pt-4 mt-2 border-t border-main" {...reg('sign-out')}>
        <button
          type="button"
          onClick={signOut}
          disabled={signingOut}
          className="flex items-center gap-1.5 border border-alt rounded-md px-3 py-1.5 text-sm text-zinc-400 hover:text-strong disabled:opacity-40"
        >
          {signingOut ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogOut className="w-4 h-4" />}
          Sign out
        </button>
      </div>
    </Pane>
  )
}
