"""SQLAlchemy models for DeviceKit — one module per domain, mirroring the mixins that
own the data today. Importing this package registers every table on ``db.Base.metadata``
(Alembic and ``create_all`` rely on that side effect).
"""
from devicekit.models.automation import Automation, AutomationRun, AutomationSchedule
from devicekit.models.fleet import DeviceGroup, DeviceTag, SavedQuery
from devicekit.models.baseline import VisualBaseline
from devicekit.models.bundle import DebugBundle
from devicekit.models.session import StreamSession
from devicekit.models.agent_device import AgentDevice
from devicekit.models.extension import InstalledExtension
from devicekit.models.notification import (
    Notification, NotificationDelivery, NotificationChannelConfig,
    NotificationPreference, NotificationRecipientSettings)

# Queue Bus + Jobs live in their own packages (plan 05) but must register on the shared
# ``Base`` here so ``create_all`` and Alembic's autogenerate see every table.
from devicekit.queue_bus.models import QueueGroup, Queue, QueueMessage
from devicekit.jobs.models import Job, ScheduledJob

__all__ = [
    "Automation",
    "AutomationRun",
    "AutomationSchedule",
    "DeviceGroup",
    "DeviceTag",
    "SavedQuery",
    "VisualBaseline",
    "DebugBundle",
    "StreamSession",
    "AgentDevice",
    "InstalledExtension",
    "Notification",
    "NotificationDelivery",
    "NotificationChannelConfig",
    "NotificationPreference",
    "NotificationRecipientSettings",
    "QueueGroup",
    "Queue",
    "QueueMessage",
    "Job",
    "ScheduledJob",
]
