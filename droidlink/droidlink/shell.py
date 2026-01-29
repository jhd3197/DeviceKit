"""Shell command execution."""

from typing import TYPE_CHECKING
from .types import ShellResult

if TYPE_CHECKING:
    from .connection import Connection


class ShellManager:
    """Execute shell commands on the device."""

    def __init__(self, conn: "Connection"):
        self._conn = conn

    def __call__(self, command: str, timeout: int = 30) -> ShellResult:
        """Execute a shell command. Usage: d.shell("ls /sdcard")"""
        data = self._conn.post_json("/shell", {"command": command, "timeout": timeout}, timeout=timeout + 5)
        return ShellResult(
            output=data.get("output", ""),
            exit_code=data.get("exit_code", -1),
        )
