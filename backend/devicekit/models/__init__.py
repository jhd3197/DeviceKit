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
from devicekit.models.command import DeviceCommand
from devicekit.models.agent_audit import AgentAuditLog
from devicekit.models.pending_agent import PendingAgent
from devicekit.models.extension import InstalledExtension
from devicekit.models.setting import Setting
from devicekit.models.metrics import (
    DeviceMetricRaw, DeviceMetricHourly, DeviceMetricDaily)
from devicekit.models.metric_alert import MetricAlertRule
from devicekit.models.notification import (
    Notification, NotificationDelivery, NotificationChannelConfig,
    NotificationPreference, NotificationRecipientSettings)
from devicekit.models.user import User, UserSession
from devicekit.models.api_key import ApiKey
from devicekit.models.audit_log import AuditLog
from devicekit.models.workspace import Workspace, WorkspaceMember, ResourceGrant
from devicekit.models.secret_vault import Vault, Secret
from devicekit.models.invitation import Invitation
from devicekit.models.fleet_policy import FleetPolicy
from devicekit.models.agent_release import AgentRelease
from devicekit.models.agent_rollout import AgentRollout
from devicekit.models.agent_update_state import AgentUpdateState
from devicekit.models.onboarding import OnboardingSession
from devicekit.models.agent_plugin import AgentPlugin
from devicekit.models.backup import Backup

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
    "DeviceCommand",
    "AgentAuditLog",
    "PendingAgent",
    "InstalledExtension",
    "Setting",
    "DeviceMetricRaw",
    "DeviceMetricHourly",
    "DeviceMetricDaily",
    "MetricAlertRule",
    "Notification",
    "NotificationDelivery",
    "NotificationChannelConfig",
    "NotificationPreference",
    "NotificationRecipientSettings",
    "User",
    "UserSession",
    "ApiKey",
    "AuditLog",
    "Workspace",
    "WorkspaceMember",
    "ResourceGrant",
    "Vault",
    "Secret",
    "Invitation",
    "FleetPolicy",
    "AgentRelease",
    "AgentRollout",
    "AgentUpdateState",
    "OnboardingSession",
    "AgentPlugin",
    "Backup",
    "QueueGroup",
    "Queue",
    "QueueMessage",
    "Job",
    "ScheduledJob",
]
