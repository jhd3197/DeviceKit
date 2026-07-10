"""AI tool contribution — bound into every per-device Prompture ToolRegistry as
``devicekit_webhook_notify__send_notification``."""
from . import notify


def register(ai):
    @ai.tool
    def send_notification(message: str) -> str:
        """Send a notification message to the configured team webhook (Slack/Discord)."""
        record = notify.send(message)
        return f"Sent (status {record['status_code']})" if not record["error"] else f"Failed: {record['error']}"
