// General settings pane (plan 12): instance name + default device timeout.
import React from 'react'
import { Pane, Field, TextInput, NumberInput, SaveBar } from './fields'
import { usePaneForm } from './usePaneForm'

const KEYS = ['general.instance_name', 'general.default_device_timeout']

export default function General({ settings, save }) {
  const f = usePaneForm(settings, KEYS, save)

  return (
    <Pane title="General" description="Instance identity and fleet-wide defaults.">
      <Field
        label="Instance name"
        help="Shown in the sidebar and page titles. Rename this node."
        htmlFor="instance-name"
      >
        <TextInput
          id="instance-name"
          value={f.draft['general.instance_name']}
          onChange={(v) => f.set('general.instance_name', v)}
          placeholder="DeviceKit"
        />
      </Field>

      <Field
        label="Default device timeout"
        help="Fallback per-command dispatch timeout for device operations."
        htmlFor="device-timeout"
      >
        <NumberInput
          id="device-timeout"
          value={f.draft['general.default_device_timeout']}
          onChange={(v) => f.set('general.default_device_timeout', v)}
          min={1}
          max={600}
          suffix="seconds"
        />
      </Field>

      {f.error && <p className="text-xs text-red-400">{f.error}</p>}
      <SaveBar dirty={f.dirty} saving={f.saving} savedAt={f.savedAt} onSave={f.persist} onReset={f.reset} />
    </Pane>
  )
}
