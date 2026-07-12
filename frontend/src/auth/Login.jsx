// Login + invite-acceptance screen (plan 20). Shown by AuthGate when the backend reports
// login_required. Handles the two-step 2FA flow (password → authenticator code) and, when the
// URL carries ?invite=<token>, an account-creation form for an invited teammate.
import React, { useEffect, useState } from 'react'
import { Loader2, ShieldCheck, KeyRound, LogIn } from 'lucide-react'
import Logo from '../components/Logo'
import { api, setSessionToken } from '../api'
import { useAuth } from './AuthContext'

const inputCls =
  'w-full bg-black border border-alt rounded-md px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-accent'

function Card({ children }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-black px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-3 mb-8 justify-center">
          <Logo size={36} className="rounded shrink-0" />
          <span className="font-bold tracking-tight text-xl">DeviceKit</span>
        </div>
        <div className="border border-main rounded-lg bg-zinc-950 p-6">{children}</div>
      </div>
    </div>
  )
}

function InviteAccept({ token, onDone }) {
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.previewInvitation(token).then(setPreview).catch((e) => setError(e.message))
  }, [token])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.acceptInvitation(token, username, password)
      // Log straight in with the new credentials.
      const r = await api.login(username, password)
      if (r.token) setSessionToken(r.token)
      onDone()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (error && !preview) {
    return (
      <Card>
        <p className="text-sm text-red-400">This invitation is not valid or has expired.</p>
      </Card>
    )
  }

  return (
    <Card>
      <h1 className="text-base font-bold mb-1">Accept invitation</h1>
      <p className="text-xs text-zinc-500 mb-5">
        {preview ? `Join as ${preview.role}. Choose a username and password.` : 'Loading…'}
      </p>
      <form onSubmit={submit} className="space-y-3">
        <input className={inputCls} placeholder="Username" value={username}
          onChange={(e) => setUsername(e.target.value)} autoFocus />
        <input className={inputCls} type="password" placeholder="Password" value={password}
          onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="text-xs text-red-400">{error}</p>}
        <button type="submit" disabled={busy || !username || !password}
          className="w-full bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 flex items-center justify-center gap-2">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
          Create account
        </button>
      </form>
    </Card>
  )
}

export default function Login() {
  const { refresh } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [mfa, setMfa] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const inviteToken = new URLSearchParams(window.location.search).get('invite')
  if (inviteToken) {
    return <InviteAccept token={inviteToken} onDone={() => { window.history.replaceState({}, '', '/'); refresh() }} />
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const r = await api.login(username, password, mfa ? code : undefined)
      if (r.token) {
        setSessionToken(r.token)
        await refresh()
        return
      }
      if (r.mfa_required) {
        setMfa(true)
        setError(mfa ? 'Invalid 2FA code' : null)
      }
    } catch (err) {
      if (err.body?.mfa_required) {
        setMfa(true)
        setError(mfa ? 'Invalid 2FA code' : null)
      } else if (err.status === 429) {
        setError(err.body?.retry_after
          ? `Too many attempts. Try again in ${Math.ceil(err.body.retry_after / 60)} min.`
          : 'Account temporarily locked.')
      } else {
        setError(err.message || 'Login failed')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <h1 className="text-base font-bold mb-1">Sign in</h1>
      <p className="text-xs text-zinc-500 mb-5">Enter your DeviceKit credentials.</p>
      <form onSubmit={submit} className="space-y-3">
        <input className={inputCls} placeholder="Username" value={username} autoFocus
          onChange={(e) => setUsername(e.target.value)} disabled={mfa} />
        <input className={inputCls} type="password" placeholder="Password" value={password}
          onChange={(e) => setPassword(e.target.value)} disabled={mfa} />
        {mfa && (
          <div className="relative">
            <KeyRound className="w-4 h-4 text-zinc-600 absolute left-3 top-1/2 -translate-y-1/2" />
            <input className={`${inputCls} pl-9 font-mono tracking-widest`} placeholder="6-digit code"
              value={code} onChange={(e) => setCode(e.target.value)} autoFocus />
          </div>
        )}
        {error && <p className="text-xs text-red-400">{error}</p>}
        <button type="submit" disabled={busy || !username || !password || (mfa && !code)}
          className="w-full bg-white text-black text-sm font-semibold px-4 py-2 rounded-md disabled:opacity-40 flex items-center justify-center gap-2">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
          {mfa ? 'Verify' : 'Sign in'}
        </button>
      </form>
    </Card>
  )
}
