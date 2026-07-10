"""DeviceKit Queue Bus — a SQL-backed, SQS-like message broker (port of ServerKit's
``queue_bus/``). The job system rides this as its transport; see ``devicekit.jobs``."""
from devicekit.queue_bus.service import QueueBusService, QueueBusError

__all__ = ["QueueBusService", "QueueBusError"]
