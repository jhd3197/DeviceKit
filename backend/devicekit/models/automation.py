"""Automation domain models: definitions, runs, and schedules.

``to_dict()`` reproduces the exact in-memory shape the AutomationMixin used, so the
``{'automations': [...], 'count': N}`` / run / schedule response envelopes and the
frontend stay untouched.
"""
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, JSON

from devicekit.db import Base


class Automation(Base):
    __tablename__ = "automations"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    steps = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)
    # plan 20 part 4: born-in-workspace. NULL = global (unscoped, pre-plan-20 behavior).
    workspace_id = Column(String, nullable=True, index=True)
    # plan 22: a tramo WorkflowDoc ({version, nodes, edges, meta}). NULL = linear
    # automation (the `steps` list stays authoritative); set = graph automation.
    graph = Column(JSON, nullable=True)
    # plan 22 part 4: per-automation inbound webhook token — the id *is* the auth
    # (POST /hooks/<token>). NULL until a webhook trigger is enabled.
    webhook_token = Column(String, nullable=True, index=True, unique=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "steps": self.steps or [],
            "tags": self.tags or [],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "workspace_id": self.workspace_id,
            "graph": self.graph,
            "webhook_token": self.webhook_token,
        }


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id = Column(String, primary_key=True)
    automation_id = Column(String, index=True)
    automation_name = Column(String, default="")
    device_id = Column(String, index=True)
    status = Column(String, default="running")
    started_at = Column(Float, index=True)
    finished_at = Column(Float, nullable=True)
    total_steps = Column(Integer, default=0)
    completed_steps = Column(Integer, default=0)
    current_step_index = Column(Integer, default=0)
    step_results = Column(JSON, default=list)
    error = Column(Text, nullable=True)
    self_heal = Column(Boolean, default=False)
    # plan 22: 'linear' (step-list run) or 'graph' (WorkflowDoc run). For graph runs,
    # step_results holds per-node records and `trigger` the payload that started it
    # ({type: manual|webhook|cron|event, ...}).
    kind = Column(String, default="linear")
    trigger = Column(JSON, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "automation_id": self.automation_id,
            "automation_name": self.automation_name or "",
            "device_id": self.device_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_steps": self.total_steps or 0,
            "completed_steps": self.completed_steps or 0,
            "current_step_index": self.current_step_index or 0,
            "step_results": self.step_results or [],
            "error": self.error,
            "self_heal": bool(self.self_heal),
            "kind": self.kind or "linear",
            "trigger": self.trigger,
        }


class AutomationSchedule(Base):
    __tablename__ = "automation_schedules"

    id = Column(String, primary_key=True)
    automation_id = Column(String, index=True)
    automation_name = Column(String, default="")
    device_id = Column(String)
    interval_minutes = Column(Float, default=0)
    enabled = Column(Boolean, default=True)
    last_run_at = Column(Float, nullable=True)
    next_run_at = Column(Float, nullable=True)
    created_at = Column(Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "automation_id": self.automation_id,
            "automation_name": self.automation_name or "",
            "device_id": self.device_id,
            "interval_minutes": self.interval_minutes,
            "enabled": bool(self.enabled),
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "created_at": self.created_at,
        }
