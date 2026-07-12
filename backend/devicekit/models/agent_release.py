"""A signed agent APK release (plan 25 part 3).

The APK bytes live on disk (``<output>/ota/apks/<id>.apk``); the row carries the metadata
the agent needs to verify a download before installing it: the pinned ``sha256``, the size,
and the Ed25519 ``signature`` over the release manifest. ``status`` lets an operator yank a
bad build so no new rollout can offer it.
"""
import time

from sqlalchemy import Column, String, Integer, Float, Text

from devicekit.db import Base

STATUS_PUBLISHED = "published"
STATUS_YANKED = "yanked"


class AgentRelease(Base):
    __tablename__ = "agent_releases"

    id = Column(String, primary_key=True)
    version_name = Column(String, nullable=False)     # e.g. "1.3.0"
    version_code = Column(Integer, nullable=False)     # e.g. 7 — the monotonic update key
    sha256 = Column(String, nullable=False)            # of the APK bytes
    size_bytes = Column(Integer, nullable=False)
    signature = Column(String, nullable=False)         # Ed25519 over the release manifest
    public_key = Column(String, nullable=False)        # hex pubkey that verifies `signature`
    filename = Column(String, nullable=True)           # original upload name (informational)
    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default=STATUS_PUBLISHED)
    created_at = Column(Float, nullable=False, default=time.time)
    created_by = Column(String, nullable=True)

    def manifest(self):
        """The signed manifest an agent verifies. These fields (and only these) are what was
        signed at creation; the download URL is served unsigned alongside because integrity
        comes from the signed ``sha256``, not the URL."""
        return {
            "release_id": self.id,
            "version_name": self.version_name,
            "version_code": self.version_code,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }

    def to_dict(self):
        return {
            "id": self.id,
            "version_name": self.version_name,
            "version_code": self.version_code,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "signature": self.signature,
            "public_key": self.public_key,
            "filename": self.filename,
            "notes": self.notes,
            "status": self.status,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }
