import React from 'react'
import { Route } from 'react-router-dom'
import ExtensionErrorBoundary from './ExtensionErrorBoundary'
import { resolveComponent } from './contributions'

// Build the list of <Route> elements contributed by active extensions (plan 04). Each
// route's element is wrapped in a per-extension error boundary so a throwing extension page
// shows a contained failure card instead of white-screening the router. Components that
// can't be resolved (no bundled module / missing export) are skipped with a dev warning.
//
// Returned as a plain array so App can spread it inside its <Routes> alongside core routes.
export function buildExtensionRoutes(routes) {
  return (routes || [])
    .map((r) => {
      const Comp = resolveComponent(r.slug, r.component)
      if (!Comp) return null
      return (
        <Route
          key={`${r.slug}:${r.path}`}
          path={r.path}
          element={
            <ExtensionErrorBoundary slug={r.slug}>
              <Comp />
            </ExtensionErrorBoundary>
          }
        />
      )
    })
    .filter(Boolean)
}
