#!/usr/bin/env node
// Lint the palette's settings omnisearch index (plan 26, mirrors ServerKit's
// scripts/check-settings-index.mjs). Fails CI when a real Settings tab has zero entries, an entry
// is malformed, points at an unknown tab, or an id is duplicated — so the deep-link surface stays
// honest as settings panes are added. Run from the repo root:  node scripts/check-settings-index.mjs
import { SETTINGS_INDEX } from '../frontend/src/data/settingsIndex.js'

// Static tabs from frontend/src/views/Settings.jsx TABS. The dynamic 'extensions' tab is excluded
// on purpose — it only appears when an installed extension contributes a panel and has no static
// cards to index. Keep this in sync with the TABS registry.
const TABS = [
  'general', 'api', 'account', 'users', 'apikeys', 'workspaces', 'vault',
  'audit', 'ai', 'streaming', 'bundles', 'notifications', 'appearance', 'about',
]

const errors = []
const counts = new Map(TABS.map((t) => [t, 0]))
const seen = new Set()

for (const e of SETTINGS_INDEX) {
  if (!e || !e.id || !e.tab || !e.label) {
    errors.push(`Malformed entry: ${JSON.stringify(e)}`)
    continue
  }
  if (seen.has(e.id)) errors.push(`Duplicate id: '${e.id}'`)
  seen.add(e.id)
  if (counts.has(e.tab)) counts.set(e.tab, counts.get(e.tab) + 1)
  else errors.push(`Entry '${e.id}' references unknown tab '${e.tab}'`)
}

for (const [tab, n] of counts) {
  if (n === 0) errors.push(`Settings tab '${tab}' has no entries in settingsIndex.js`)
}

if (errors.length) {
  console.error('settingsIndex.js check FAILED:')
  for (const e of errors) console.error('  - ' + e)
  process.exit(1)
}

console.log(`settingsIndex.js OK — ${SETTINGS_INDEX.length} entries across ${TABS.length} tabs`)
