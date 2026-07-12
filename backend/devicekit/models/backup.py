"""A backup of DeviceKit's own state (plan 25 part 6).

One row per backup: where the tarball + separately-stored manifest live, the verify ladder
level reached (``none → listed → hashed → drilled``), and the latest restore-drill result.
``chain_prev`` links backups so the manifest can carry chain refs. The drill fields drive the
edge-triggered ``restore_confidence`` alert (fire once on failure, once on recovery).
"""
import time

from sqlalchemy import Column, String, Float, Integer, JSON

from devicekit.db import Base

# verify ladder
VERIFY_NONE = "none"
VERIFY_LISTED = "listed"
VERIFY_HASHED = "hashed"
VERIFY_DRILLED = "drilled"
VERIFY_LEVELS = [VERIFY_NONE, VERIFY_LISTED, VERIFY_HASHED, VERIFY_DRILLED]

# drill outcomes
DRILL_PASSED = "passed"
DRILL_FAILED = "failed"
DRILL_SKIPPED_NO_SPACE = "skipped_no_space"


class Backup(Base):
    __tablename__ = "backups"

    id = Column(String, primary_key=True)
    created_at = Column(Float, nullable=False, default=time.time)
    path = Column(String, nullable=False)          # tarball path
    manifest_path = Column(String, nullable=False)  # manifest.json path (stored SEPARATELY)
    manifest = Column(JSON, nullable=False)        # embedded copy for quick reads
    size_bytes = Column(Integer, nullable=False, default=0)
    verify_level = Column(String, nullable=False, default=VERIFY_NONE)
    verify_detail = Column(JSON, nullable=True)
    drill_status = Column(String, nullable=True)   # passed | failed | skipped_no_space
    drill_detail = Column(JSON, nullable=True)
    drilled_at = Column(Float, nullable=True)
    chain_prev = Column(String, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "created_at": self.created_at,
            "path": self.path,
            "manifest_path": self.manifest_path,
            "manifest": self.manifest or {},
            "size_bytes": self.size_bytes,
            "verify_level": self.verify_level,
            "verify_detail": self.verify_detail,
            "drill_status": self.drill_status,
            "drill_detail": self.drill_detail,
            "drilled_at": self.drilled_at,
            "chain_prev": self.chain_prev,
        }
