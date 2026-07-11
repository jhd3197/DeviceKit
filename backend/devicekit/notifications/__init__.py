"""Notification bus for DeviceKit (plan 06).

A single producer call — ``NotificationService.send(event_key, data, ...)`` — turns a fleet
event ("device went offline", "automation failed") into a persisted, rendered notification
that reaches operators through one or more channels:

* **in-app** — immediate, rides the existing SSE broadcast (no Socket.IO);
* **webhook** — Slack/Discord-compatible POST, delivered asynchronously on the Queue Bus;
* **email** — SMTP, delivered asynchronously (secrets encrypted at rest).

The *event catalog* (``catalog.py``) maps an ``event_key`` to a title/severity/category and a
deep link, so adding an alert type is a catalog entry, not new plumbing — and extensions can
``register()`` their own. Deep links are computed and persisted at send time, so route
refactors never break old notifications.

Composed onto the ``Client`` via :class:`devicekit.mixins.notifications.NotificationsMixin`.
"""
from devicekit.notifications import catalog
from devicekit.notifications.service import NotificationService

__all__ = ["catalog", "NotificationService"]
