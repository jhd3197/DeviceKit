# Plan 06 — Notification Bus & Notification Center

**Status:** proposed
**Inspired by:** ServerKit's `backend/app/notifications/` (event catalog, per-channel
delivery, digests) and `NotificationsContext` / `NotificationBell` on the frontend
**Depends on:** 01 (delivery rows), 05 (async channel delivery rides the queue)

## Problem

DeviceKit has an `alerts.py` mixin (in-memory alert list) and SSE broadcasts, but no
concept of *delivering* an alert anywhere: no email/webhook, no per-event routing, no
read/unread, no history that survives restart. For a fleet tool, "device went offline,"
"automation failed," "battery critical," and "visual regression detected" are exactly
the events an operator wants pushed to Slack/email, not just visible if a browser tab
happens to be open.

## What ServerKit built

- **One producer call:** `notify.send(event_key, to, data)` — non-blocking, safe to
  call from anywhere (jobs, request handlers, extensions).
- **Event catalog** (`catalog.py`): `event_key → {title template, severity, category,
  deep link}`. Adding an alert type = adding a catalog entry, not code. **Extensible by
  plugins** via `register()`.
- **Delivery planning:** per-recipient preferences + quiet hours decide which channels
  fire; each delivery is a persisted row; non-instant channels enqueue on the Queue Bus
  and a `NotificationConsumer` renders + transmits.
- **Channel adapters** (`channels/`): in-app, email (SMTP/SendGrid/Postmark/SES/Mailgun,
  secrets encrypted), chat webhooks (Slack/Discord-compatible). Digest batching for
  noisy events.
- **Deep links are computed and persisted at send time**, so route refactors don't
  break old notifications.
- Frontend: Socket.IO-pushed unread badge, optimistic mark-read, full history page.

## Design for DeviceKit

### Backend

1. `backend/devicekit/notifications/` package: `catalog.py`, `service.py` (producer),
   `consumer.py` (queue-driven delivery), `channels/{inapp,webhook,email}.py`.
   Models (plan 01): `Notification`, `NotificationDelivery`, plus a settings-backed
   channel config (webhook URLs, SMTP creds — secrets encrypted at rest).
2. Seed catalog with DeviceKit's real events:
   `device.offline`, `device.online`, `device.battery.critical`,
   `device.storage.low`, `automation.run.failed`, `automation.run.healed`
   (self-heal fired — worth knowing!), `regression.detected`, `bundle.created`,
   `pipeline.build.failed`, `agent.enrolled`.
3. Producer call sites: the heartbeat reaper (plan 07) emits `device.offline`;
   the automation job handler emits run events; visual regression emits on diff.
   Existing `alerts.py` mixin becomes a thin shim over the bus (or is absorbed by it).
4. **In-app channel rides the existing SSE** (`subscribeToEvents`) — no Socket.IO
   needed; a `notification` SSE event carries the rendered payload.
5. Webhook channel first (cheapest, highest value for CI labs), email second.
6. Extensions (plan 03): `sdk.notify.send(...)` + catalog registration → a Slack/
   Discord notifier is a natural early extension.

### Frontend

1. `NotificationsContext`-style provider: unread count fed by the SSE event,
   optimistic `markRead`/`markAllRead` with reconcile-on-refetch.
2. Bell dropdown in the sidebar/topbar: severity dots, deep links to the subject
   (device page, run detail).
3. `/notifications` history view; per-event-type channel preferences in Settings
   (plan 12).

## Phases

1. Catalog + models + producer + in-app channel over SSE + bell UI.
2. Webhook channel + delivery rows + retry via queue (plan 05).
3. Preferences (per-event mute, quiet hours) + email channel + digests.

## Definition of done

Kill a device's agent → within the heartbeat timeout an operator sees the unread badge,
the bell shows "Pixel 7 went offline" deep-linking to the device page, and a configured
Slack webhook received the same event; all of it visible in `/notifications` after a
backend restart.
