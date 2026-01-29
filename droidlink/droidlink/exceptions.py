"""droidlink exceptions."""


class DroidLinkError(Exception):
    """Base exception for droidlink."""
    pass


class DeviceNotFoundError(DroidLinkError):
    """No device found or device not reachable."""
    pass


class ConnectionError(DroidLinkError):
    """Failed to connect to device agent."""
    pass


class AdbError(DroidLinkError):
    """ADB command failed."""
    pass


class UiElementNotFoundError(DroidLinkError):
    """UI element matching selector was not found."""
    pass


class AgentNotRunningError(DroidLinkError):
    """Agent app is not running or HTTP server not started."""
    pass


class ShellCommandError(DroidLinkError):
    """Shell command execution failed."""

    def __init__(self, command: str, exit_code: int, output: str):
        self.command = command
        self.exit_code = exit_code
        self.output = output
        super().__init__(f"Command '{command}' failed (exit={exit_code}): {output}")
