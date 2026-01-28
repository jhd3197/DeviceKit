import uuid
import json
import re
import hashlib
import logging
from slugify import slugify

logger = logging.getLogger(__name__)


class ToolsMixin:
    """Utility methods: data conversion, text processing, JSON extraction."""

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

    def remove_json_extras(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = cleaned.replace("null", '""')
        json_match = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
        if not json_match:
            return ""
        json_content = json_match.group()
        json_content = json_content.replace("\u201c", '"').replace("\u201d", '"')
        json_content = json_content.replace("\u2018", "'").replace("\u2019", "'")
        json_content = json_content.replace('"null"', '""').replace("'null'", '""')
        json_content = json_content.replace("null", '""').replace('""""', '""')
        return json_content

    def extract_json_from_text(self, response: str) -> dict:
        json_content = self.remove_json_extras(response)
        if not json_content:
            return {}
        try:
            return json.loads(json_content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from text")
            return {}
