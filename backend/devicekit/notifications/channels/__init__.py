"""Notification channel adapters (plan 06).

Each channel turns a persisted :class:`Notification` into a delivery on some transport:

* ``inapp``  — synchronous, rides the existing SSE broadcast (plan 06.1);
* ``webhook`` — Slack/Discord-compatible POST, async on the Queue Bus (plan 06.2);
* ``email``  — SMTP, async, secrets encrypted at rest (plan 06.3).

Async channels expose ``render(notif, config) -> payload`` and ``transmit(payload, config)``
so the ``NotificationConsumer`` can render + send from a plain delivery row without host
internals.
"""
