"""Email notification channel (plan 06.3).

Sends a notification over SMTP using the stdlib (`smtplib` + `email.message`). Config
(host/port/user/password/from/to) lives in the encrypted channel config; the password is
decrypted in-process before the send. Delivery is asynchronous — the ``NotificationConsumer``
calls :func:`send` from a queue-driven job so a slow/misconfigured mail server retries via the
Queue Bus rather than blocking the producer.
"""
import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

CHANNEL = "email"
TIMEOUT_SECONDS = 20


def _recipients(config):
    raw = config.get("to_addrs") or ""
    return [a.strip() for a in raw.replace(";", ",").split(",") if a.strip()]


def build_message(notif, config):
    """Construct an :class:`EmailMessage` for ``notif``. Raises if from/to are missing."""
    to_addrs = _recipients(config)
    from_addr = config.get("from_addr") or config.get("smtp_user")
    if not from_addr:
        raise ValueError("Email 'from_addr' is not configured")
    if not to_addrs:
        raise ValueError("Email 'to_addrs' is not configured")

    severity = (notif.get("severity") or "info").upper()
    msg = EmailMessage()
    msg["Subject"] = f"[DeviceKit · {severity}] {notif.get('title', 'Notification')}"
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    body = notif.get("title", "")
    if notif.get("body"):
        body += f"\n\n{notif['body']}"
    if notif.get("deep_link"):
        body += f"\n\nView: {notif['deep_link']}"
    msg.set_content(body)
    return msg


def send(notif, config, timeout=TIMEOUT_SECONDS):
    """Send ``notif`` via SMTP. Raises on any failure so the delivery job retries."""
    host = config.get("smtp_host")
    if not host:
        raise ValueError("Email 'smtp_host' is not configured")
    port = int(config.get("smtp_port") or 587)
    user = config.get("smtp_user")
    password = config.get("smtp_password")
    use_tls = config.get("use_tls", True)

    msg = build_message(notif, config)
    with smtplib.SMTP(host, port, timeout=timeout) as server:
        if use_tls:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)
    return {"sent_to": msg["To"]}
