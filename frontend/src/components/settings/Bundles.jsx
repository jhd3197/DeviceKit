// Debug Bundles settings pane (plan 12): retention window + share-token lifetime.
//
// Retention drives `cleanup_old_bundles`; share lifetime is the default expiry for new
// share links (backend reads `client.bundle_retention_days()` /
// `client.share_token_lifetime_minutes()`).
import React from 'react'
import { Pane, Field, NumberInput, SaveBar } from './fields'
import { usePaneForm } from './usePaneForm'

const KEYS = ['bundles.retention_days', 'bundles.share_token_lifetime_minutes']

export default function Bundles({ settings, save, register }) {
  const reg = register || (() => ({}))
  const f = usePaneForm(settings, KEYS, save)

  return (
    <Pane
      title="Debug Bundles"
      description="Retention and sharing for auto-generated failure debug bundles."
    >
      <Field
        label="Retention window"
        help="Bundles older than this are deleted on the next cleanup pass."
        htmlFor="bundle-retention"
        register={reg('retention')}
      >
        <NumberInput
          id="bundle-retention"
          value={f.draft['bundles.retention_days']}
          onChange={(v) => f.set('bundles.retention_days', v)}
          min={1}
          max={365}
          suffix="days"
        />
      </Field>

      <Field
        label="Share-link lifetime"
        help="Default expiry for a bundle share link when no explicit duration is given."
        htmlFor="share-lifetime"
        register={reg('share-link-lifetime')}
      >
        <NumberInput
          id="share-lifetime"
          value={f.draft['bundles.share_token_lifetime_minutes']}
          onChange={(v) => f.set('bundles.share_token_lifetime_minutes', v)}
          min={5}
          max={20160}
          suffix="minutes"
        />
      </Field>

      {f.error && <p className="text-xs text-red-400">{f.error}</p>}
      <SaveBar dirty={f.dirty} saving={f.saving} savedAt={f.savedAt} onSave={f.persist} onReset={f.reset} />
    </Pane>
  )
}
