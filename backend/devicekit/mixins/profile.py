import uuid
import time
import logging

logger = logging.getLogger(__name__)


class ProfileMixin:
    """AI profile management for devices."""

    _profiles = []

    def create_profile(self, device_id, name, personality="", niche="",
                       interests=None, behavior_patterns=None, apps=None):
        profile = {
            "id": str(uuid.uuid4()),
            "device_id": device_id,
            "name": name,
            "personality": personality,
            "niche": niche,
            "interests": interests or [],
            "behavior_patterns": behavior_patterns or {
                "scroll_speed": "medium",
                "engagement_rate": 0.5,
                "session_duration_min": 30,
                "break_between_sessions_min": 15,
            },
            "apps": apps or [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._profiles.append(profile)
        logger.info(f"Created profile '{name}' for device {device_id}")
        return profile

    def get_profile(self, profile_id):
        return next((p for p in self._profiles if p["id"] == profile_id), None)

    def get_profile_by_device(self, device_id):
        return next((p for p in self._profiles if p["device_id"] == device_id), None)

    def list_profiles(self):
        return list(self._profiles)

    def update_profile(self, profile_id, updates):
        profile = self.get_profile(profile_id)
        if not profile:
            return None
        for key in ("name", "personality", "niche", "interests",
                     "behavior_patterns", "apps", "device_id"):
            if key in updates:
                profile[key] = updates[key]
        profile["updated_at"] = time.time()
        return profile

    def delete_profile(self, profile_id):
        before = len(self._profiles)
        self._profiles = [p for p in self._profiles if p["id"] != profile_id]
        deleted = len(self._profiles) < before
        if deleted:
            logger.info(f"Deleted profile {profile_id}")
        return deleted
