// AuthGate (plan 20): decides login screen vs the app. Renders children when authenticated (or
// in solo mode); shows <Login/> when the backend reports login_required or the URL carries an
// invite token. Wraps the whole app in index.jsx so no per-view change is needed.
import React from 'react'
import { Loader2 } from 'lucide-react'
import { useAuth } from './AuthContext'
import Login from './Login'

export default function AuthGate({ children }) {
  const { session, loading } = useAuth()
  const hasInvite = !!new URLSearchParams(window.location.search).get('invite')

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black text-zinc-500">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    )
  }

  if (hasInvite || session?.login_required) {
    return <Login />
  }
  return children
}
