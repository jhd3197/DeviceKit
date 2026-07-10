import uuid
import time
import logging
import json
import io
import zipfile
import hashlib
import os

from devicekit.db import session_scope
from devicekit.models import DebugBundle

logger = logging.getLogger(__name__)

BUNDLE_RETENTION_DAYS = 30


class DebugBundleMixin:
    """Failure Debug Bundles — auto-package diagnostics on failure.

    Bundle metadata is persisted (DebugBundle rows); the ZIP payload is written to disk
    under ``<output_dir>/debug_bundles/<id>.zip``. Share tokens are short-lived and stay
    in memory on purpose.
    """

    _share_tokens = {}  # token -> {bundle_id, expires_at}  (ephemeral)

    def _bundle_dir(self):
        base = os.path.join(getattr(self, 'output_dir', 'output'), 'debug_bundles')
        os.makedirs(base, exist_ok=True)
        return base

    def _bundle_zip_path(self, bundle_id):
        return os.path.join(self._bundle_dir(), f'{bundle_id}.zip')

    # -----------------------------------------------------------
    # Bundle generation
    # -----------------------------------------------------------

    def generate_debug_bundle(self, device_id, trigger='manual', context=None):
        """Collect all diagnostics for a device and package into a ZIP bundle.

        Args:
            device_id: Target device
            trigger: 'manual', 'automation_failure', 'pipeline_failure'
            context: Optional dict with extra info (automation_id, run_id, step_index, error)

        Returns:
            Bundle metadata dict (without raw data — use get_bundle_zip for download)
        """
        context = context or {}
        bundle_id = str(uuid.uuid4())
        started_at = time.time()
        logger.info(f"Generating debug bundle {bundle_id} for device {device_id} (trigger={trigger})")

        collected = {}

        # 1. Screenshot
        try:
            screenshot_data = self.take_screenshot(device_id)
            if screenshot_data:
                collected['screenshot.png'] = screenshot_data
        except Exception as e:
            logger.warning(f"Bundle: screenshot failed: {e}")
            collected['screenshot_error.txt'] = str(e).encode('utf-8')

        # 2. Logcat (last 100 lines)
        try:
            logcat_output = self.run_adb_command(
                ['shell', 'logcat', '-d', '-t', '100'], device=device_id
            )
            if logcat_output:
                collected['logcat.txt'] = logcat_output.encode('utf-8') if isinstance(logcat_output, str) else logcat_output
        except Exception as e:
            logger.warning(f"Bundle: logcat failed: {e}")
            collected['logcat_error.txt'] = str(e).encode('utf-8')

        # 3. Device state (CPU, RAM, battery, active app)
        state = {}
        try:
            info = self.get_device_info(device_id)
            if info:
                state['device_info'] = info
        except Exception:
            pass

        try:
            battery = self.get_device_battery(device=device_id)
            state['battery'] = battery
        except Exception:
            pass

        try:
            # Current foreground app
            fg = self.run_adb_command(
                ['shell', 'dumpsys', 'activity', 'recents', '|', 'grep', 'mFocusedApp'],
                device=device_id,
            )
            state['focused_app'] = fg.strip() if fg else ''
        except Exception:
            pass

        state['trigger'] = trigger
        state['context'] = context
        state['collected_at'] = time.time()
        collected['state.json'] = json.dumps(state, indent=2, default=str).encode('utf-8')

        # 4. UI Hierarchy XML
        try:
            self.run_adb_command(['shell', 'uiautomator', 'dump', '/sdcard/window_dump.xml'], device=device_id)
            hierarchy = self.run_adb_command(['shell', 'cat', '/sdcard/window_dump.xml'], device=device_id)
            if hierarchy:
                collected['ui_hierarchy.xml'] = hierarchy.encode('utf-8') if isinstance(hierarchy, str) else hierarchy
            self.run_adb_command(['shell', 'rm', '/sdcard/window_dump.xml'], device=device_id)
        except Exception as e:
            logger.warning(f"Bundle: UI hierarchy failed: {e}")

        # 5. Last 10 agent actions (from activity log)
        try:
            activities = self.get_activities(limit=10, device_id_filter=device_id)
            collected['actions.json'] = json.dumps(activities, indent=2, default=str).encode('utf-8')
        except Exception:
            collected['actions.json'] = b'[]'

        # 6. Device properties
        try:
            props = self.run_adb_command(['shell', 'getprop'], device=device_id)
            if props:
                collected['properties.json'] = json.dumps(
                    {'raw_getprop': props}, indent=2
                ).encode('utf-8')
        except Exception:
            pass

        # Build ZIP in memory, then persist to disk
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename, data in collected.items():
                zf.writestr(filename, data)
        zip_bytes = zip_buffer.getvalue()

        zip_path = self._bundle_zip_path(bundle_id)
        with open(zip_path, 'wb') as f:
            f.write(zip_bytes)

        generation_ms = int((time.time() - started_at) * 1000)
        with session_scope() as s:
            bundle = DebugBundle(
                id=bundle_id,
                device_id=device_id,
                trigger=trigger,
                context=context,
                files=list(collected.keys()),
                size_bytes=len(zip_bytes),
                created_at=started_at,
                generation_ms=generation_ms,
                ai_analysis=None,
                zip_path=zip_path,
            )
            s.add(bundle)
            s.flush()
            result = bundle.to_dict()
        logger.info(
            f"Debug bundle {bundle_id} generated: {len(collected)} files, "
            f"{len(zip_bytes)} bytes, {generation_ms}ms"
        )
        return result

    # -----------------------------------------------------------
    # Bundle retrieval
    # -----------------------------------------------------------

    def get_debug_bundle(self, bundle_id):
        """Get bundle metadata by ID."""
        with session_scope() as s:
            bundle = s.get(DebugBundle, bundle_id)
            return bundle.to_dict() if bundle else None

    def get_bundle_zip(self, bundle_id):
        """Get raw ZIP bytes for download."""
        with session_scope() as s:
            bundle = s.get(DebugBundle, bundle_id)
            zip_path = bundle.zip_path if bundle else None
        if zip_path and os.path.exists(zip_path):
            with open(zip_path, 'rb') as f:
                return f.read()
        return None

    def list_debug_bundles(self, device_id=None, trigger=None, limit=50):
        """List bundles with optional filters."""
        with session_scope() as s:
            q = s.query(DebugBundle)
            if device_id:
                q = q.filter(DebugBundle.device_id == device_id)
            if trigger:
                q = q.filter(DebugBundle.trigger == trigger)
            q = q.order_by(DebugBundle.created_at.desc()).limit(limit)
            return [b.to_dict() for b in q.all()]

    def delete_debug_bundle(self, bundle_id):
        """Delete a bundle by ID."""
        with session_scope() as s:
            bundle = s.get(DebugBundle, bundle_id)
            if not bundle:
                return False
            zip_path = bundle.zip_path
            s.delete(bundle)
        # Remove the ZIP from disk and any share tokens for this bundle
        if zip_path and os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except OSError:
                pass
        self._share_tokens = {
            t: v for t, v in self._share_tokens.items()
            if v['bundle_id'] != bundle_id
        }
        logger.info(f"Deleted debug bundle {bundle_id}")
        return True

    # -----------------------------------------------------------
    # AI failure analysis
    # -----------------------------------------------------------

    def analyze_debug_bundle(self, bundle_id):
        """Send bundle contents to AI for root cause analysis."""
        bundle = self.get_debug_bundle(bundle_id)
        if not bundle:
            return None

        # Extract text content from zip for analysis
        zip_data = self.get_bundle_zip(bundle_id)
        if not zip_data:
            return {'error': 'Bundle data not available'}

        text_contents = {}
        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            for name in zf.namelist():
                if name.endswith(('.txt', '.json', '.xml')):
                    try:
                        text_contents[name] = zf.read(name).decode('utf-8', errors='replace')
                    except Exception:
                        pass

        # Build prompt for AI
        context = bundle.get('context', {})
        prompt_parts = [
            "Analyze this Android device failure debug bundle and provide:",
            "1. Root cause hypothesis",
            "2. Suggested fix or next steps",
            "3. Severity assessment (low/medium/high/critical)",
            "",
            f"Trigger: {bundle.get('trigger', 'unknown')}",
        ]
        if context.get('error'):
            prompt_parts.append(f"Error: {context['error']}")
        if context.get('step_type'):
            prompt_parts.append(f"Failed step type: {context['step_type']}")

        prompt_parts.append("\n--- Bundle Contents ---")
        for name, content in text_contents.items():
            # Truncate large files
            truncated = content[:3000] if len(content) > 3000 else content
            prompt_parts.append(f"\n=== {name} ===\n{truncated}")

        prompt = "\n".join(prompt_parts)

        try:
            from prompture import Prompture
            ai = Prompture()
            response = ai.chat(prompt)
            analysis = response if isinstance(response, str) else str(response)
            ai_analysis = {
                'analysis': analysis,
                'analyzed_at': time.time(),
                'files_analyzed': list(text_contents.keys()),
            }
            with session_scope() as s:
                row = s.get(DebugBundle, bundle_id)
                if row:
                    row.ai_analysis = ai_analysis
            logger.info(f"AI analysis complete for bundle {bundle_id}")
            return ai_analysis
        except ImportError:
            logger.warning("Prompture not available for AI analysis")
            return {'error': 'AI analysis requires the prompture package'}
        except Exception as e:
            logger.error(f"AI analysis failed for bundle {bundle_id}: {e}")
            return {'error': str(e)}

    # -----------------------------------------------------------
    # Share links
    # -----------------------------------------------------------

    def generate_share_link(self, bundle_id, expires_hours=24):
        """Generate a time-limited share token for a bundle."""
        bundle = self.get_debug_bundle(bundle_id)
        if not bundle:
            return None

        token = hashlib.sha256(f"{bundle_id}-{time.time()}-{uuid.uuid4()}".encode()).hexdigest()[:32]
        self._share_tokens[token] = {
            'bundle_id': bundle_id,
            'expires_at': time.time() + (expires_hours * 3600),
            'created_at': time.time(),
        }
        logger.info(f"Share link generated for bundle {bundle_id}: token={token[:8]}...")
        return {
            'token': token,
            'bundle_id': bundle_id,
            'expires_at': self._share_tokens[token]['expires_at'],
            'expires_hours': expires_hours,
        }

    def get_bundle_by_share_token(self, token):
        """Validate share token and return bundle ZIP data if valid."""
        entry = self._share_tokens.get(token)
        if not entry:
            return None, 'Invalid share token'
        if time.time() > entry['expires_at']:
            del self._share_tokens[token]
            return None, 'Share link expired'
        return self.get_bundle_zip(entry['bundle_id']), None

    # -----------------------------------------------------------
    # Retention policy
    # -----------------------------------------------------------

    def cleanup_old_bundles(self, max_age_days=None):
        """Remove bundles older than max_age_days (default: BUNDLE_RETENTION_DAYS)."""
        max_age = (max_age_days or BUNDLE_RETENTION_DAYS) * 86400
        cutoff = time.time() - max_age
        with session_scope() as s:
            expired = s.query(DebugBundle).filter(DebugBundle.created_at < cutoff).all()
            expired_specs = [(b.id, b.zip_path) for b in expired]
            for b in expired:
                s.delete(b)
        removed = len(expired_specs)

        # Remove ZIPs from disk and clean share tokens for removed bundles
        if expired_specs:
            expired_ids = {bid for bid, _ in expired_specs}
            for _, zip_path in expired_specs:
                if zip_path and os.path.exists(zip_path):
                    try:
                        os.remove(zip_path)
                    except OSError:
                        pass
            self._share_tokens = {
                t: v for t, v in self._share_tokens.items()
                if v['bundle_id'] not in expired_ids
            }

        if removed:
            logger.info(f"Retention cleanup: removed {removed} bundles older than {max_age_days or BUNDLE_RETENTION_DAYS} days")
        return removed
