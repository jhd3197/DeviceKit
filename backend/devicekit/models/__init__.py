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
]
