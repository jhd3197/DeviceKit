import React from 'react'
import { useContributions, resolveComponent } from './contributions'
import ExtensionErrorBoundary from './ExtensionErrorBoundary'

// Named mount point for extension widgets (plan 04, port of ServerKit's PluginSlot). Every
// active extension whose manifest contributes a widget for `name` renders here, in
// declaration order, each wrapped in a per-extension error boundary. Host context is passed
// through as props (e.g. <ExtensionSlot name="run-detail.panels" run={run} />) so widgets
// can react to the surrounding page.
//
// Seed slots (plan 04): `dashboard.top`, `node-detail.tabs`, `run-detail.panels`,
// `settings.panels`. Renders nothing when no widget targets the slot, so hosts can drop a
// slot anywhere with zero layout cost until an extension fills it.
export default function ExtensionSlot({ name, className, children, ...props }) {
  const { envelope } = useContributions()
  const widgets = (envelope.widgets || []).filter((w) => w.slot === name)
  if (!widgets.length) return null

  const rendered = widgets
    .map((w) => {
      const Comp = resolveComponent(w.slug, w.component)
      if (!Comp) return null
      return (
        <ExtensionErrorBoundary key={`${w.slug}:${w.component}`} slug={w.slug} compact>
          <Comp {...props} />
        </ExtensionErrorBoundary>
      )
    })
    .filter(Boolean)

  if (!rendered.length) return null
  return className ? <div className={className}>{rendered}</div> : <>{rendered}</>
}
