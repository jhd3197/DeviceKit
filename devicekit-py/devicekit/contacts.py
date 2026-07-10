"""Contacts and SMS reading."""

from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Connection


class ContactsManager:
    """
    Read device contacts and SMS.

    Usage:
        contacts = d.contacts.list()
        results = d.contacts.search("John")
        messages = d.sms.list()
        conversations = d.sms.conversations()
    """

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def list(self, limit: int = 100) -> List[dict]:
        """List contacts."""
        data = self._conn.get_json("/contacts", params={"limit": limit})
        return data.get("contacts", [])

    def search(self, query: str) -> List[dict]:
        """Search contacts by name."""
        data = self._conn.get_json("/contacts/search", params={"q": query})
        return data.get("contacts", [])


class SmsManager:
    """
    Read SMS messages.

    Usage:
        messages = d.sms.list(limit=20)
        messages = d.sms.list(address="+1234567890")
        conversations = d.sms.conversations()
    """

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def list(self, limit: int = 50, address: Optional[str] = None) -> List[dict]:
        """List SMS messages, optionally filtered by address."""
        params = {"limit": limit}
        if address:
            params["address"] = address
        data = self._conn.get_json("/sms", params=params)
        return data.get("messages", [])

    def conversations(self, limit: int = 20) -> List[dict]:
        """List SMS conversations (grouped by address)."""
        data = self._conn.get_json("/sms/conversations", params={"limit": limit})
        return data.get("conversations", [])
