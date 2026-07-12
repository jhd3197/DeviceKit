// Streaming settings pane (plan 12): default fps/quality + recording retention.
//
// These defaults feed new stream and recording sessions when a viewer doesn't pin values
// (backend routes read `client.streaming_defaults()`).
import React from 'react'
import { Pane, Field, NumberInput, SaveBar } from './fields'
import { usePaneForm } from './usePaneForm'

const KEYS = [
  'streaming.default_fps',
  'streaming.default_quality',
  'streaming.recording_retention_days',
]

export default function Streaming({ settings, save, register }) {
  const reg = register || (() => ({}))
  const f = usePaneForm(settings, KEYS, save)

  return (
    <Pane title="Streaming" description="Defaults for live device streams and session recordings.">
      <Field
        label="Default frame rate"
        help="Frames per second for new streams (1–30)."
        htmlFor="stream-fps"
        register={reg('stream-fps')}
      >
        <NumberInput
          id="stream-fps"
          value={f.draft['streaming.default_fps']}
          onChange={(v) => f.set('streaming.default_fps', v)}
          min={1}
          max={30}
          suffix="fps"
        />
      </Field>

      <Field
        label="Default quality"
        help="JPEG quality for new streams (10–100). Lower = less bandwidth."
        htmlFor="stream-quality"
        register={reg('stream-quality')}
      >
        <NumberInput
          id="stream-quality"
          value={f.draft['streaming.default_quality']}
          onChange={(v) => f.set('streaming.default_quality', v)}
          min={10}
          max={100}
          suffix="%"
        />
      </Field>

      <Field
        label="Recording retention"
        help="How long recorded sessions are kept before cleanup."
        htmlFor="rec-retention"
        register={reg('recording-retention')}
      >
        <NumberInput
          id="rec-retention"
          value={f.draft['streaming.recording_retention_days']}
          onChange={(v) => f.set('streaming.recording_retention_days', v)}
          min={1}
          max={365}
          suffix="days"
        />
      </Field>

      {f.error && <p className="text-xs text-red-400">{f.error}</p>}
      <SaveBar dirty={f.dirty} saving={f.saving} savedAt={f.savedAt} onSave={f.persist} onReset={f.reset} />
    </Pane>
  )
}
