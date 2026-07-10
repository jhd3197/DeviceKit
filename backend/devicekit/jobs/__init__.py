"""DeviceKit unified job system (port of ServerKit's ``jobs/``).

``Job`` rows + a single ``JobConsumer`` + a ``kind → handler`` registry replace the scattered
per-feature daemon threads; ``ScheduledJob`` rows + a ``JobScheduler`` ticker replace the
hand-rolled interval loops. The Queue Bus (``devicekit.queue_bus``) is the transport.

The ``JobsMixin`` (``devicekit.mixins.jobs``) wires this into the ``Client``: it registers the
core job kinds, starts the consumer + scheduler at server boot, and exposes the façade the
API blueprint and SDK call.
"""
from devicekit.jobs.service import JobService, ScheduledJobService, GROUP_SLUG, QUEUE_SLUG
from devicekit.jobs.consumer import JobConsumer
from devicekit.jobs.scheduler import JobScheduler
from devicekit.jobs import registry

__all__ = [
    "JobService", "ScheduledJobService", "JobConsumer", "JobScheduler", "registry",
    "GROUP_SLUG", "QUEUE_SLUG",
]
