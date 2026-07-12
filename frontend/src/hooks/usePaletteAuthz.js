// Palette authorization (plan 26, ported from ServerKit's hooks/usePaletteAuthz.js).
//
// The command palette must never surface something the user can't reach: admin-only settings
// cards (Users, API Keys, Vault, Audit Log) are dropped for non-admins, mirroring the Settings
// shell hiding those tabs. Returns an `allow(item)` predicate the palette filters every candidate
// through — items carry `adminOnly` (settings index) and may later carry other visibility flags.
import { useCallback } from 'react'
import { useAuth } from '../auth/AuthContext'

export function usePaletteAuthz() {
  const { isAdmin } = useAuth()

  const allow = useCallback(
    (item) => {
      if (item?.adminOnly && !isAdmin) return false
      return true
    },
    [isAdmin]
  )

  return { isAdmin, allow }
}
