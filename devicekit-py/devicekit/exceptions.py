"""devicekit exceptions."""


class DeviceKitError(Exception):
    """Base exception for devicekit."""
    pass


class DeviceNotFoundError(DeviceKitError):
    """No device found or device not reachable."""
    pass


class ConnectionError(DeviceKitError):
    """Failed to connect to device agent."""
    pass


class AdbError(DeviceKitError):
    """ADB command failed."""
    pass


class UiElementNotFoundError(DeviceKitError):
    """UI element matching selector was not found."""
    pass


class AgentNotRunningError(DeviceKitError):
    """Agent app is not running or HTTP server not started."""
    pass


class ShellCommandError(DeviceKitError):
    """Shell command execution failed."""

    def __init__(self, command: str, exit_code: int, output: str):
        self.command = command
        self.exit_code = exit_code
        self.output = output
        super().__init__(f"Command '{command}' failed (exit={exit_code}): {output}")
