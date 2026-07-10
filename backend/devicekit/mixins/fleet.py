import uuid
import time
import logging

from devicekit.db import session_scope
from devicekit.models import DeviceGroup, DeviceTag

logger = logging.getLogger(__name__)


class FleetMixin:
    """Fleet management: device groups, tags, and bulk operations."""

    # ── Group CRUD ──────────────────────────────────────────────

    def create_device_group(self, name, description='', color='#10b981', tags=None, device_ids=None):
        now = time.time()
        with session_scope() as s:
            group = DeviceGroup(
                id=str(uuid.uuid4()),
                name=name,
                description=description,
                color=color,
                tags=tags or [],
                device_ids=device_ids or [],
                created_at=now,
                updated_at=now,
            )
            s.add(group)
            s.flush()
            result = group.to_dict()
        logger.info(f"Device group created: {name} ({result['id']})")
        return result

    def get_device_group(self, group_id):
        with session_scope() as s:
            group = s.get(DeviceGroup, group_id)
            return group.to_dict() if group else None

    def list_device_groups(self):
        with session_scope() as s:
            return [g.to_dict() for g in s.query(DeviceGroup).all()]

    def update_device_group(self, group_id, updates):
        with session_scope() as s:
            group = s.get(DeviceGroup, group_id)
            if not group:
                return None
            for key in ('name', 'description', 'color', 'tags', 'device_ids'):
                if key in updates:
                    setattr(group, key, updates[key])
            group.updated_at = time.time()
            s.flush()
            return group.to_dict()

    def delete_device_group(self, group_id):
        with session_scope() as s:
            group = s.get(DeviceGroup, group_id)
            if not group:
                return False
            s.delete(group)
        logger.info(f"Device group deleted: {group_id}")
        return True

    # ── Group membership ────────────────────────────────────────

    def add_device_to_group(self, group_id, device_id):
        with session_scope() as s:
            group = s.get(DeviceGroup, group_id)
            if not group:
                return None
            ids = list(group.device_ids or [])
            if device_id not in ids:
                ids.append(device_id)
                group.device_ids = ids
                group.updated_at = time.time()
            s.flush()
            return group.to_dict()

    def remove_device_from_group(self, group_id, device_id):
        with session_scope() as s:
            group = s.get(DeviceGroup, group_id)
            if not group:
                return None
            ids = list(group.device_ids or [])
            if device_id in ids:
                ids.remove(device_id)
                group.device_ids = ids
                group.updated_at = time.time()
            s.flush()
            return group.to_dict()

    def get_groups_for_device(self, device_id):
        with session_scope() as s:
            return [
                g.to_dict()
                for g in s.query(DeviceGroup).all()
                if device_id in (g.device_ids or [])
            ]

    # ── Per-device tags ─────────────────────────────────────────

    def set_device_tags(self, device_id, tags):
        tags = list(tags)
        with session_scope() as s:
            row = s.get(DeviceTag, device_id)
            if row:
                row.tags = tags
            else:
                s.add(DeviceTag(device_id=device_id, tags=tags))
        return tags

    def get_device_tags(self, device_id):
        with session_scope() as s:
            row = s.get(DeviceTag, device_id)
            return list(row.tags or []) if row else []
