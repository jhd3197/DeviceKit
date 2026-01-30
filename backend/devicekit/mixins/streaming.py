import logging
import os
import threading
import time
import uuid
import tempfile

import requests

logger = logging.getLogger(__name__)


class StreamingMixin:
    _stream_viewers = {}       # device_id -> int (active viewer count)
    _stream_viewers_lock = threading.Lock()
    _recording_sessions = {}   # session_id -> session dict
    _recording_lock = threading.Lock()

    def proxy_device_stream(self, device_id, fps=10, quality=50):
        """Open an MJPEG stream from the agent and yield chunks for Flask Response."""
        agent_ip, agent_port = self._resolve_agent_stream_address(device_id)
        if not agent_ip:
            return None

        fps = max(1, min(30, int(fps)))
        quality = max(10, min(100, int(quality)))

        url = f"http://{agent_ip}:{agent_port}/screen/stream"
        try:
            resp = requests.get(
                url,
                params={"fps": fps, "quality": quality},
                stream=True,
                timeout=(5, None),
            )
            if not resp.ok:
                logger.warning(f"Stream request failed for {device_id}: {resp.status_code}")
                return None

            content_type = resp.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=droidlink_frame")

            def generate():
                with self._stream_viewers_lock:
                    self._stream_viewers[device_id] = self._stream_viewers.get(device_id, 0) + 1
                try:
                    for chunk in resp.iter_content(chunk_size=4096):
                        if chunk:
                            yield chunk
                except GeneratorExit:
                    pass
                except Exception as e:
                    logger.debug(f"Stream ended for {device_id}: {e}")
                finally:
                    with self._stream_viewers_lock:
                        count = self._stream_viewers.get(device_id, 1) - 1
                        if count <= 0:
                            self._stream_viewers.pop(device_id, None)
                        else:
                            self._stream_viewers[device_id] = count
                    resp.close()

            return generate(), content_type

        except requests.exceptions.ConnectionError:
            logger.warning(f"Could not connect to agent stream for {device_id} at {url}")
            return None
        except Exception as e:
            logger.warning(f"Stream proxy error for {device_id}: {e}")
            return None

    def get_stream_viewers(self, device_id):
        """Return count of active stream viewers for a device."""
        with self._stream_viewers_lock:
            return self._stream_viewers.get(device_id, 0)

    def is_stream_available(self, device_id):
        """Check if streaming is available for a device."""
        agent_ip, agent_port = self._resolve_agent_stream_address(device_id)
        return agent_ip is not None

    def _resolve_agent_stream_address(self, device_id):
        """Resolve the agent IP and port for streaming. Returns (ip, port) or (None, None)."""
        # Try agent device registry first
        if hasattr(self, '_find_agent_device_for_stream'):
            agent_data = self._find_agent_device_for_stream(device_id)
        else:
            agent_data = None

        if agent_data:
            info = agent_data.get('info', {})
            agent_ip = info.get('ip')
            agent_port = info.get('agent_port', 9800)
            if agent_ip:
                return agent_ip, agent_port

        # Fallback: try localhost with ADB-forwarded port
        return '127.0.0.1', 9800

    # -----------------------------------------------------------
    # Session Recording
    # -----------------------------------------------------------

    def start_recording_session(self, device_id, fps=10, quality=50):
        """Start a stream recording session. Captures frames in a background thread."""
        session_id = str(uuid.uuid4())
        tmp_dir = tempfile.mkdtemp(prefix=f"devicekit_rec_{session_id[:8]}_")
        fps = max(1, min(30, int(fps)))
        quality = max(10, min(100, int(quality)))

        session = {
            'id': session_id,
            'device_id': device_id,
            'fps': fps,
            'quality': quality,
            'started_at': time.time(),
            'stopped_at': None,
            'frame_count': 0,
            'events': [],
            'frames_dir': tmp_dir,
            'active': True,
            '_stop_event': threading.Event(),
        }

        with self._recording_lock:
            self._recording_sessions[session_id] = session

        # Start background capture thread
        thread = threading.Thread(
            target=self._recording_capture_thread,
            args=(session_id,),
            daemon=True,
        )
        thread.start()
        session['_thread'] = thread

        logger.info(f"Recording session started: {session_id} for device {device_id}")
        return {
            'session_id': session_id,
            'device_id': device_id,
            'started_at': session['started_at'],
            'fps': fps,
            'quality': quality,
        }

    def _recording_capture_thread(self, session_id):
        """Background thread that captures MJPEG frames to disk."""
        with self._recording_lock:
            session = self._recording_sessions.get(session_id)
        if not session:
            return

        device_id = session['device_id']
        agent_ip, agent_port = self._resolve_agent_stream_address(device_id)
        if not agent_ip:
            logger.warning(f"Recording {session_id}: could not resolve agent address")
            session['active'] = False
            return

        url = f"http://{agent_ip}:{agent_port}/screen/stream"
        stop_event = session['_stop_event']
        frame_interval = 1.0 / session['fps']

        try:
            resp = requests.get(
                url,
                params={"fps": session['fps'], "quality": session['quality']},
                stream=True,
                timeout=(5, None),
            )
            if not resp.ok:
                logger.warning(f"Recording {session_id}: stream request failed")
                session['active'] = False
                return

            buffer = b""
            frame_index = 0
            boundary = b"--droidlink_frame"

            for chunk in resp.iter_content(chunk_size=4096):
                if stop_event.is_set():
                    break
                if not chunk:
                    continue

                buffer += chunk

                # Extract complete frames from the multipart stream
                while boundary in buffer:
                    parts = buffer.split(boundary, 1)
                    frame_data = parts[0]

                    # Extract JPEG data (skip headers)
                    if b"\r\n\r\n" in frame_data:
                        header_end = frame_data.index(b"\r\n\r\n") + 4
                        jpeg_data = frame_data[header_end:].strip()
                        if jpeg_data and len(jpeg_data) > 100:
                            frame_path = os.path.join(
                                session['frames_dir'],
                                f"frame_{frame_index:06d}.jpg"
                            )
                            try:
                                with open(frame_path, 'wb') as f:
                                    f.write(jpeg_data)
                                frame_index += 1
                                session['frame_count'] = frame_index
                            except Exception as e:
                                logger.debug(f"Recording frame write error: {e}")

                    buffer = parts[1] if len(parts) > 1 else b""

            resp.close()

        except Exception as e:
            logger.debug(f"Recording {session_id} capture ended: {e}")
        finally:
            session['active'] = False

    def stop_recording_session(self, session_id):
        """Stop a recording session and return metadata."""
        with self._recording_lock:
            session = self._recording_sessions.get(session_id)
        if not session:
            return None

        session['_stop_event'].set()
        session['stopped_at'] = time.time()
        session['active'] = False

        # Wait briefly for thread to finish
        thread = session.get('_thread')
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

        duration_ms = int((session['stopped_at'] - session['started_at']) * 1000)

        return {
            'session_id': session_id,
            'device_id': session['device_id'],
            'frame_count': session['frame_count'],
            'duration_ms': duration_ms,
            'events': session['events'],
            'fps': session['fps'],
            'started_at': session['started_at'],
            'stopped_at': session['stopped_at'],
        }

    def get_recording_sessions(self, device_id):
        """List all recording sessions for a device."""
        sessions = []
        with self._recording_lock:
            for session in self._recording_sessions.values():
                if session['device_id'] == device_id:
                    duration_ms = 0
                    if session.get('stopped_at') and session.get('started_at'):
                        duration_ms = int((session['stopped_at'] - session['started_at']) * 1000)
                    elif session.get('started_at'):
                        duration_ms = int((time.time() - session['started_at']) * 1000)
                    sessions.append({
                        'session_id': session['id'],
                        'device_id': session['device_id'],
                        'frame_count': session['frame_count'],
                        'duration_ms': duration_ms,
                        'fps': session['fps'],
                        'active': session['active'],
                        'started_at': session['started_at'],
                        'stopped_at': session.get('stopped_at'),
                        'event_count': len(session['events']),
                    })
        return sorted(sessions, key=lambda s: s['started_at'], reverse=True)

    def get_recording_metadata(self, session_id):
        """Return recording metadata (frame count, fps, duration, events)."""
        with self._recording_lock:
            session = self._recording_sessions.get(session_id)
        if not session:
            return None

        duration_ms = 0
        if session.get('stopped_at') and session.get('started_at'):
            duration_ms = int((session['stopped_at'] - session['started_at']) * 1000)
        elif session.get('started_at'):
            duration_ms = int((time.time() - session['started_at']) * 1000)

        return {
            'session_id': session_id,
            'device_id': session['device_id'],
            'frame_count': session['frame_count'],
            'duration_ms': duration_ms,
            'fps': session['fps'],
            'active': session['active'],
            'started_at': session['started_at'],
            'stopped_at': session.get('stopped_at'),
            'events': session['events'],
        }

    def get_recording_frame(self, session_id, frame_index):
        """Return a single frame as JPEG bytes."""
        with self._recording_lock:
            session = self._recording_sessions.get(session_id)
        if not session:
            return None

        frame_path = os.path.join(
            session['frames_dir'],
            f"frame_{int(frame_index):06d}.jpg"
        )
        if not os.path.exists(frame_path):
            return None

        try:
            with open(frame_path, 'rb') as f:
                return f.read()
        except Exception:
            return None

    def record_stream_event(self, session_id, event_data):
        """Record an input event during an active recording session."""
        with self._recording_lock:
            session = self._recording_sessions.get(session_id)
        if not session or not session['active']:
            return None

        event = {
            'timestamp': time.time(),
            'relative_ms': int((time.time() - session['started_at']) * 1000),
            'frame_index': session['frame_count'],
            **event_data,
        }
        session['events'].append(event)
        return len(session['events'])
