// Notifications settings pane (plan 12 × plan 06). Surfaces the existing channel config +
// per-event preference editors inside Settings so they live where users look for them —
// reusing the same components the Notifications view already renders (single source of
// truth for both).
import React from 'react'
import { Pane } from './fields'
import NotificationChannels from '../NotificationChannels'
import NotificationPreferences from '../NotificationPreferences'

export default function NotificationsPane() {
  return (
    <Pane
      title="Notifications"
      description="Delivery channels and per-event preferences for fleet notifications."
    >
      <NotificationChannels />
      <div className="pt-2 border-t border-main" />
      <NotificationPreferences />
    </Pane>
  )
}
