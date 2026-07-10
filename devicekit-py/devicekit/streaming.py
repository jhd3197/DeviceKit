"""Screen mirroring via MJPEG stream."""

import threading
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Connection


class ScreenStream:
    """
    MJPEG screen streaming from device.

    Usage:
        # Save frames to files
        stream = d.screen_stream(fps=5)
        stream.on_frame(lambda frame_bytes, idx: open(f"frame_{idx}.png", "wb").write(frame_bytes))
        stream.start()

        # Or iterate frames
        for i, frame in enumerate(d.screen_stream(fps=2)):
            with open(f"frame_{i}.png", "wb") as f:
                f.write(frame)
            if i > 10:
                break
    """

    def __init__(self, conn: "Connection", fps: int = 5, quality: int = 50):
        self._conn = conn
        self._fps = fps
        self._quality = quality
        self._frame_handler: Optional[Callable] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._frame_count = 0

    def on_frame(self, handler: Callable) -> "ScreenStream":
        """Register a frame handler: handler(frame_bytes, frame_index)."""
        self._frame_handler = handler
        return self

    def start(self) -> "ScreenStream":
        """Start streaming in a background thread."""
        if self._running:
            return self
        self._running = True
        self._frame_count = 0
        self._thread = threading.Thread(target=self._stream, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        """Stop streaming."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _stream(self):
        try:
            resp = self._conn.get(
                "/screen/stream",
                params={"fps": self._fps, "quality": self._quality},
                stream=True,
                timeout=None,
            )
            boundary = b"droidlink_frame"
            buffer = b""

            for chunk in resp.iter_content(chunk_size=8192):
                if not self._running:
                    break
                buffer += chunk

                while boundary in buffer:
                    # Find boundary
                    idx = buffer.find(boundary)
                    if idx == -1:
                        break

                    # Find header end (\r\n\r\n)
                    header_end = buffer.find(b"\r\n\r\n", idx)
                    if header_end == -1:
                        break

                    # Parse Content-Length from header
                    header = buffer[idx:header_end].decode("utf-8", errors="ignore")
                    content_length = 0
                    for line in header.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())

                    data_start = header_end + 4
                    data_end = data_start + content_length

                    if len(buffer) < data_end:
                        break  # Need more data

                    frame_data = buffer[data_start:data_end]
                    buffer = buffer[data_end:]

                    if frame_data and self._frame_handler:
                        self._frame_handler(frame_data, self._frame_count)
                    self._frame_count += 1

        except Exception:
            pass
        finally:
            self._running = False

    def __iter__(self):
        """Iterate over frames as bytes."""
        resp = self._conn.get(
            "/screen/stream",
            params={"fps": self._fps, "quality": self._quality},
            stream=True,
            timeout=None,
        )
        boundary = b"droidlink_frame"
        buffer = b""

        for chunk in resp.iter_content(chunk_size=8192):
            buffer += chunk
            while boundary in buffer:
                idx = buffer.find(boundary)
                if idx == -1:
                    break
                header_end = buffer.find(b"\r\n\r\n", idx)
                if header_end == -1:
                    break
                header = buffer[idx:header_end].decode("utf-8", errors="ignore")
                content_length = 0
                for line in header.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        content_length = int(line.split(":")[1].strip())
                data_start = header_end + 4
                data_end = data_start + content_length
                if len(buffer) < data_end:
                    break
                frame_data = buffer[data_start:data_end]
                buffer = buffer[data_end:]
                if frame_data:
                    yield frame_data

    def save_frames(self, directory: str, count: int = 10, prefix: str = "frame"):
        """Save a number of frames to a directory."""
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        for i, frame in enumerate(self):
            (path / f"{prefix}_{i:04d}.png").write_bytes(frame)
            if i + 1 >= count:
                break

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
