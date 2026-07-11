# Plan 06 — Notification Bus & Notification Center

**Status:** ✅ complete — all 3 phases shipped (catalog + in-app bell; webhook + queue delivery; preferences + email + digests)
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

1. ✅ Catalog + models + producer + in-app channel over SSE + bell UI.
   Shipped: `devicekit/notifications/` (`catalog.py` with `register()` + 10 seeded fleet
   events, `service.py` producer, `channels/inapp.py`); `models/notification.py`
   (`Notification` + `NotificationDelivery`, epoch timestamps); `NotificationsMixin`
   (`notify_event`, read/query façade, retention prune job+schedule); `routes/notifications.py`
   blueprint; migration `c3d4e5f6a7b8`. Producer call sites wired: automation run
   failed/healed, device offline (heartbeat reaper stopgap in `agent-device/status`),
   battery critical, storage low. SDK `notify` seam live (`send` + `register_event`, tracked
   for extension teardown). Frontend: `store/notifications.js` (single-SSE singleton),
   `NotificationBell` in the sidebar (unread badge, optimistic mark-read, deep links),
   `/notifications` history view. Tests: `test_notifications.py` (14).
2. ✅ Webhook channel + delivery rows + retry via queue (plan 05).
   Shipped: `channels/webhook.py` (Slack/Discord/generic render + transmit), `crypto.py`
   (Fernet at-rest secret encryption keyed on `DEVICEKIT_SECRET_KEY`, dev fallback),
   `config.py` (`NotificationChannelService`: per-channel enable/config, secret masking +
   mask-resubmit preservation, severity-threshold gating), `consumer.py`
   (`notification.deliver` job kind — render+transmit, success→sent, failure→raise so the
   Queue Bus retries/dead-letters, delivery row mirrors outcome). Producer
   `_plan_async_channels` writes a pending delivery per enabled channel and enqueues one
   delivery job (target persisted as a non-secret host hint). Channel API
   (`GET/PUT /notifications/channels[/<channel>]`, `POST .../test`). Migration
   `d4e5f6a7b8c9`. Frontend: `NotificationChannels` config panel (schema-driven, masked
   secrets, Test button) behind the Notifications "Channels" toggle. Tests:
   `test_notification_channels.py` (11).
3. ✅ Preferences (per-event mute, quiet hours) + email channel + digests.
   Shipped: `channels/email.py` (SMTP via stdlib, encrypted creds, retries on the delivery
   job); `preferences.py` (`PreferenceService`: full/per-channel mutes, quiet-hours window
   with critical break-through, digest membership; `flush_digests` batches pending markers
   into one summary per recipient/channel). Producer wired: full mute drops the event,
   in-app mute keeps history, quiet hours suppress async (in-app kept), digested events drop
   a marker instead of pushing. Models `NotificationPreference` + `NotificationRecipientSettings`;
   `notification.digest.flush` job + 5-min schedule. Preferences API
   (`GET/PUT /notifications/preferences`, `PUT .../mute`, `POST /notifications/digests/flush`).
   Migration `e5f6a7b8c9d0`. Frontend: `NotificationPreferences` panel (quiet hours, digest
   config + event picker, per-event mute list) behind the Notifications "Preferences" toggle;
   `NotificationChannels` now also surfaces the email channel. Tests:
   `test_notification_preferences.py` (12).

## Deviations / notes

- **Device-offline producer** rides the existing stale-heartbeat sweep in
  `GET /agent-device/status` (15s threshold) rather than the dedicated heartbeat reaper,
  which is Plan 07 (Phase 29) — the notification fires today and will move to the reaper when
  it lands.
- **`regression.detected`** is seeded in the catalog and firable via the SDK/producer, but no
  core call site was wired (visual-regression verdicts live deep inside `screenshot_assert`
  step execution); wire it opportunistically with the Plan 07 reaper work.
- **Digest cadence** is a fixed 5-min global flush; `digest_window_minutes` is retained as a
  per-recipient hint for a future finer-grained scheduler.
- **`DEVICEKIT_SECRET_KEY`** gates channel-secret encryption; unset in dev uses an insecure
  deterministic key (logged once). Set it in any real deployment.

## Definition of done

Kill a device's agent → within the heartbeat timeout an operator sees the unread badge,
the bell shows "Pixel 7 went offline" deep-linking to the device page, and a configured
Slack webhook received the same event; all of it visible in `/notifications` after a
backend restart.
