import uuid
import time
import logging

logger = logging.getLogger(__name__)


class FleetMixin:
    """Fleet management: device groups, tags, and bulk operations."""

    _device_groups = []
    _device_tags = {}  # device_id -> [tag, ...]

    # ── Group CRUD ──────────────────────────────────────────────

    def create_device_group(self, name, description='', color='#10b981', tags=None, device_ids=None):
        group = {
            'id': str(uuid.uuid4()),
            'name': name,
            'description': description,
            'color': color,
            'tags': tags or [],
            'device_ids': device_ids or [],
            'created_at': time.time(),
            'updated_at': time.time(),
        }
        self._device_groups.append(group)
        logger.info(f"Device group created: {name} ({group['id']})")
        return group

    def get_device_group(self, group_id):
        for g in self._device_groups:
            if g['id'] == group_id:
                return g
        return None

    def list_device_groups(self):
        return list(self._device_groups)

    def update_device_group(self, group_id, updates):
        group = self.get_device_group(group_id)
        if not group:
            return None
        for key in ('name', 'description', 'color', 'tags', 'device_ids'):
            if key in updates:
                group[key] = updates[key]
        group['updated_at'] = time.time()
        return group

    def delete_device_group(self, group_id):
        for i, g in enumerate(self._device_groups):
            if g['id'] == group_id:
                self._device_groups.pop(i)
                logger.info(f"Device group deleted: {group_id}")
                return True
        return False

    # ── Group membership ────────────────────────────────────────

    def add_device_to_group(self, group_id, device_id):
        group = self.get_device_group(group_id)
        if not group:
            return None
        if device_id not in group['device_ids']:
            group['device_ids'].append(device_id)
            group['updated_at'] = time.time()
        return group

    def remove_device_from_group(self, group_id, device_id):
        group = self.get_device_group(group_id)
        if not group:
            return None
        if device_id in group['device_ids']:
            group['device_ids'].remove(device_id)
            group['updated_at'] = time.time()
        return group

    def get_groups_for_device(self, device_id):
        return [g for g in self._device_groups if device_id in g['device_ids']]

    # ── Per-device tags ─────────────────────────────────────────

    def set_device_tags(self, device_id, tags):
        self._device_tags[device_id] = list(tags)
        return self._device_tags[device_id]

    def get_device_tags(self, device_id):
        return self._device_tags.get(device_id, [])
