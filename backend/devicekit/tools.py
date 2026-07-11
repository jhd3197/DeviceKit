import uuid
import re
import hashlib
import logging
from slugify import slugify

logger = logging.getLogger(__name__)


class ToolsMixin:
    """Utility methods: data conversion and text processing."""

    def generate_guid(self):
        return str(uuid.uuid4())

    def to_slug(self, value):
        return slugify(value)

    def to_bool(self, value):
        return str(value).lower() in ("yes", "true", "t", "1", "on", "si", "verdadero")

    def to_int(self, value):
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    def canonicalize_text(self, input_text):
        text = input_text.strip()
        text = re.sub(r'\s+', ' ', text)
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        return text

    def get_text_hash(self, input_text):
        canonical_text = self.canonicalize_text(input_text)
        hash_digest = hashlib.md5(canonical_text.encode('utf-8')).digest()
        return str(uuid.UUID(bytes=hash_digest))

    def format_elapsed_time(self, elapsed):
        if elapsed < 60:
            return f"{elapsed:.2f} seconds"
        elif elapsed < 3600:
            minutes = int(elapsed // 60)
            seconds = elapsed % 60
            return f"{minutes} minute(s), {seconds:.2f} second(s)"
        else:
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = elapsed % 60
            return f"{hours} hour(s), {minutes} minute(s), {seconds:.2f} second(s)"
