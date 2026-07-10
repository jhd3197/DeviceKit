"""Stream recording-session metadata model.

Captured frames stay on disk (``frames_dir``); this row persists the session metadata and
the recorded interaction ``events`` so past recordings survive a restart and remain
playable. Live capture state (the stop event, the capture thread) is ephemeral and stays
in memory while a session is active.
"""
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, JSON

from devicekit.db import Base


class StreamSession(Base):
    __tablename__ = "stream_sessions"

    id = Column(String, primary_key=True)
    device_id = Column(String, index=True)
    fps = Column(Integer, default=10)
    quality = Column(Integer, default=50)
    started_at = Column(Float, index=True)
    stopped_at = Column(Float, nullable=True)
    frame_count = Column(Integer, default=0)
    events = Column(JSON, default=list)
    frames_dir = Column(Text, nullable=True)
    active = Column(Boolean, default=False)

    def duration_ms(self):
        if self.stopped_at and self.started_at:
            return int((self.stopped_at - self.started_at) * 1000)
        return 0

    def to_dict(self):
        return {
            "session_id": self.id,
            "device_id": self.device_id,
            "frame_count": self.frame_count or 0,
            "duration_ms": self.duration_ms(),
            "fps": self.fps,
            "active": bool(self.active),
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "events": self.events or [],
            "event_count": len(self.events or []),
        }
