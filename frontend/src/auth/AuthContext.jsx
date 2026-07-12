// Auth session context (plan 20). Loads GET /auth/session on mount and exposes the current
// principal + login-required state to the whole app. In solo mode (auth disabled, no users) the
// backend reports authenticated:true with no token, so nothing changes for the classic setup.
import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, setSessionToken } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const s = await api.getAuthSession()
      setSession(s)
      return s
    } catch (e) {
      // A hard failure (backend down) — treat as "not logged in but not blocking".
      setSession({ authenticated: false, login_required: false, has_users: false, error: e.message })
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      /* ignore */
    }
    setSessionToken('')
    await refresh()
  }, [refresh])

  const value = {
    session,
    loading,
    refresh,
    logout,
    principal: session?.principal || null,
    isAdmin: !!session?.principal?.is_admin,
    twofa: session?.twofa || null,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}
