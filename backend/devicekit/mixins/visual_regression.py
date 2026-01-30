import uuid
import time
import logging
import base64
import threading
import io
import json
import math

logger = logging.getLogger(__name__)

# Lightweight SSIM implementation (no numpy/scipy dependency)
# Operates on raw pixel luminance values from JPEG bytes


def _decode_jpeg_to_pixels(jpeg_bytes):
    """Decode JPEG bytes to (width, height, luminance_list) using PIL if available, else raw estimate."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(jpeg_bytes)).convert('L')  # grayscale
        w, h = img.size
        pixels = list(img.getdata())
        return w, h, pixels
    except ImportError:
        # Fallback: return None so caller knows SSIM isn't available
        return None, None, None


def _compute_ssim(pixels_a, pixels_b, width, height, mask_regions=None):
    """Compute SSIM between two grayscale pixel arrays. Returns 0-100 float.
    mask_regions is a list of {x, y, w, h} dicts — pixels inside masks are excluded."""
    if len(pixels_a) != len(pixels_b):
        return 0.0

    # Apply mask: build set of masked indices
    masked = set()
    if mask_regions:
        for region in mask_regions:
            rx, ry, rw, rh = int(region.get('x', 0)), int(region.get('y', 0)), int(region.get('w', 0)), int(region.get('h', 0))
            for row in range(ry, min(ry + rh, height)):
                for col in range(rx, min(rx + rw, width)):
                    masked.add(row * width + col)

    # Filter out masked pixels
    a_vals = []
    b_vals = []
    for i in range(len(pixels_a)):
        if i not in masked:
            a_vals.append(pixels_a[i])
            b_vals.append(pixels_b[i])

    n = len(a_vals)
    if n == 0:
        return 100.0  # all masked = trivially same

    # SSIM constants
    L = 255.0
    k1, k2 = 0.01, 0.03
    c1 = (k1 * L) ** 2
    c2 = (k2 * L) ** 2

    mean_a = sum(a_vals) / n
    mean_b = sum(b_vals) / n

    var_a = sum((x - mean_a) ** 2 for x in a_vals) / n
    var_b = sum((x - mean_b) ** 2 for x in b_vals) / n
    cov_ab = sum((a_vals[i] - mean_a) * (b_vals[i] - mean_b) for i in range(n)) / n

    numerator = (2 * mean_a * mean_b + c1) * (2 * cov_ab + c2)
    denominator = (mean_a ** 2 + mean_b ** 2 + c1) * (var_a + var_b + c2)

    if denominator == 0:
        return 100.0

    ssim = numerator / denominator
    return max(0.0, min(100.0, ssim * 100))


def _compute_diff_regions(pixels_a, pixels_b, width, height, block_size=16, diff_threshold=30):
    """Compute diff regions as list of {x, y, w, h, intensity} blocks where images differ."""
    regions = []
    for by in range(0, height, block_size):
        for bx in range(0, width, block_size):
            bw = min(block_size, width - bx)
            bh = min(block_size, height - by)
            total_diff = 0
            pixel_count = 0
            for row in range(by, by + bh):
                for col in range(bx, bx + bw):
                    idx = row * width + col
                    if idx < len(pixels_a) and idx < len(pixels_b):
                        total_diff += abs(pixels_a[idx] - pixels_b[idx])
                        pixel_count += 1
            if pixel_count > 0:
                avg_diff = total_diff / pixel_count
                if avg_diff > diff_threshold:
                    regions.append({
                        'x': bx, 'y': by, 'w': bw, 'h': bh,
                        'intensity': round(min(avg_diff / 255.0, 1.0), 3),
                    })
    return regions


AI_DIFF_SYSTEM_PROMPT = """You are a visual regression testing assistant for Android device UI testing.

You are comparing two screenshots: a baseline and a current screenshot.
Your job is to determine if the visual differences are meaningful UI changes or just noise.

Noise examples: timestamps, clocks, battery percentage, signal bars, animated content, cursor blinking, ad rotations.
Meaningful changes: missing buttons, different text content, layout shifts, color changes, missing elements, new elements.

Respond ONLY with valid JSON:
{
  "verdict": "pass" or "fail" or "needs_review",
  "confidence": 0.0 to 1.0,
  "summary": "Brief explanation of what changed",
  "meaningful_changes": ["list of meaningful differences"],
  "noise_items": ["list of noise/ignorable differences"]
}

Do not include any markdown formatting or code fences in your response."""


class VisualRegressionMixin:
    """Visual regression testing: baseline management, SSIM comparison, AI-powered diff analysis."""

    _vr_baselines = []  # list of baseline dicts
    _vr_baselines_lock = threading.Lock()

    # -----------------------------------------------------------
    # Baseline Management
    # -----------------------------------------------------------

    def create_baseline(self, automation_id, step_index, image_data, device_model=None,
                        resolution=None, label=None, mask_regions=None):
        """Store a baseline screenshot for an automation step."""
        baseline_id = str(uuid.uuid4())
        baseline = {
            'id': baseline_id,
            'automation_id': automation_id,
            'step_index': step_index,
            'device_model': device_model or 'default',
            'resolution': resolution or 'default',
            'label': label or f'Step {step_index} baseline',
            'image_b64': base64.b64encode(image_data).decode('ascii'),
            'image_size': len(image_data),
            'mask_regions': mask_regions or [],
            'version': 1,
            'created_at': time.time(),
            'updated_at': time.time(),
        }
        with self._vr_baselines_lock:
            self._vr_baselines.append(baseline)
        logger.info(f"Created baseline {baseline_id} for automation {automation_id} step {step_index}")
        return {k: v for k, v in baseline.items() if k != 'image_b64'}

    def get_baseline(self, baseline_id):
        """Get a baseline by ID."""
        with self._vr_baselines_lock:
            return next((b for b in self._vr_baselines if b['id'] == baseline_id), None)

    def get_baseline_image(self, baseline_id):
        """Get baseline image bytes."""
        baseline = self.get_baseline(baseline_id)
        if not baseline:
            return None
        return base64.b64decode(baseline['image_b64'])

    def list_baselines(self, automation_id):
        """List baselines for an automation (without image data)."""
        with self._vr_baselines_lock:
            results = [b for b in self._vr_baselines if b['automation_id'] == automation_id]
        return [{k: v for k, v in b.items() if k != 'image_b64'} for b in results]

    def update_baseline(self, baseline_id, image_data=None, mask_regions=None, label=None):
        """Re-capture or update a baseline."""
        baseline = self.get_baseline(baseline_id)
        if not baseline:
            return None
        if image_data:
            baseline['image_b64'] = base64.b64encode(image_data).decode('ascii')
            baseline['image_size'] = len(image_data)
            baseline['version'] = baseline.get('version', 1) + 1
        if mask_regions is not None:
            baseline['mask_regions'] = mask_regions
        if label is not None:
            baseline['label'] = label
        baseline['updated_at'] = time.time()
        logger.info(f"Updated baseline {baseline_id} (v{baseline.get('version', 1)})")
        return {k: v for k, v in baseline.items() if k != 'image_b64'}

    def delete_baseline(self, baseline_id):
        """Delete a baseline."""
        with self._vr_baselines_lock:
            before = len(self._vr_baselines)
            self._vr_baselines = [b for b in self._vr_baselines if b['id'] != baseline_id]
            return len(self._vr_baselines) < before

    def find_baseline(self, automation_id, step_index, device_model=None, resolution=None):
        """Find the best matching baseline for a step, preferring device-specific baselines."""
        with self._vr_baselines_lock:
            candidates = [
                b for b in self._vr_baselines
                if b['automation_id'] == automation_id and b['step_index'] == step_index
            ]

        if not candidates:
            return None

        # Prefer exact device model + resolution match
        if device_model and resolution:
            exact = [b for b in candidates if b['device_model'] == device_model and b['resolution'] == resolution]
            if exact:
                return exact[-1]  # most recent

        # Then device model match
        if device_model:
            model_match = [b for b in candidates if b['device_model'] == device_model]
            if model_match:
                return model_match[-1]

        # Fall back to default / any
        return candidates[-1]

    # -----------------------------------------------------------
    # Screenshot Comparison
    # -----------------------------------------------------------

    def compare_screenshot(self, current_image_data, baseline_id=None, threshold=95.0,
                           use_ai=True, device_id=None, automation_id=None, step_index=None):
        """Compare a screenshot against a baseline. Returns comparison result dict."""
        # Resolve baseline
        baseline = None
        if baseline_id:
            baseline = self.get_baseline(baseline_id)
        elif automation_id is not None and step_index is not None:
            # Try to find by automation + step
            device_model = None
            resolution = None
            if device_id:
                try:
                    d = self.get_device(device_id)
                    info = d.info
                    device_model = info.get('productName', 'default')
                    resolution = f"{info.get('displayWidth', 0)}x{info.get('displayHeight', 0)}"
                except Exception:
                    pass
            baseline = self.find_baseline(automation_id, step_index, device_model, resolution)

        if not baseline:
            return {
                'passed': False,
                'ssim': 0,
                'threshold': threshold,
                'error': 'No baseline found',
                'verdict': 'no_baseline',
            }

        baseline_image = base64.b64decode(baseline['image_b64'])
        mask_regions = baseline.get('mask_regions', [])

        # Compute SSIM
        w_a, h_a, pix_a = _decode_jpeg_to_pixels(baseline_image)
        w_b, h_b, pix_b = _decode_jpeg_to_pixels(current_image_data)

        if pix_a is None or pix_b is None:
            return {
                'passed': False,
                'ssim': 0,
                'threshold': threshold,
                'error': 'PIL not available for SSIM computation',
                'verdict': 'error',
                'baseline_id': baseline['id'],
            }

        # Resize if different dimensions (use smaller as reference)
        if (w_a, h_a) != (w_b, h_b):
            # Re-decode at matching resolution
            try:
                from PIL import Image
                img_a = Image.open(io.BytesIO(baseline_image)).convert('L')
                img_b = Image.open(io.BytesIO(current_image_data)).convert('L')
                # Resize current to baseline dimensions
                img_b = img_b.resize((w_a, h_a), Image.LANCZOS)
                pix_b = list(img_b.getdata())
                w_b, h_b = w_a, h_a
            except Exception as e:
                logger.warning(f"Resize failed: {e}")

        ssim = _compute_ssim(pix_a, pix_b, w_a, h_a, mask_regions)
        diff_regions = _compute_diff_regions(pix_a, pix_b, w_a, h_a) if ssim < threshold else []

        result = {
            'passed': ssim >= threshold,
            'ssim': round(ssim, 2),
            'threshold': threshold,
            'baseline_id': baseline['id'],
            'baseline_version': baseline.get('version', 1),
            'diff_regions': diff_regions,
            'diff_region_count': len(diff_regions),
            'verdict': 'pass' if ssim >= threshold else 'fail',
            'current_image_b64': base64.b64encode(current_image_data).decode('ascii'),
        }

        # AI analysis when threshold exceeded
        if not result['passed'] and use_ai:
            try:
                ai_result = self._ai_diff_analysis(baseline_image, current_image_data, ssim, threshold)
                result['ai_analysis'] = ai_result.get('summary', '')
                result['ai_verdict'] = ai_result.get('verdict', 'fail')
                result['ai_confidence'] = ai_result.get('confidence', 0)
                result['ai_meaningful_changes'] = ai_result.get('meaningful_changes', [])
                result['ai_noise_items'] = ai_result.get('noise_items', [])
                # If AI says pass (noise only), override verdict
                if ai_result.get('verdict') == 'pass' and ai_result.get('confidence', 0) >= 0.8:
                    result['passed'] = True
                    result['verdict'] = 'pass_ai'
            except Exception as e:
                logger.warning(f"AI diff analysis failed: {e}")
                result['ai_analysis'] = f"AI analysis unavailable: {e}"

        return result

    def _ai_diff_analysis(self, baseline_image, current_image, ssim, threshold):
        """Use Prompture to analyze visual diff."""
        from prompture import Conversation, UsageSession

        session = UsageSession()
        model = self._get_nl_model() if hasattr(self, '_get_nl_model') else 'gpt-4o-mini'
        callbacks = self._nl_usage_callbacks(session) if hasattr(self, '_nl_usage_callbacks') else None

        conv = Conversation(
            model_name=model,
            system_prompt=AI_DIFF_SYSTEM_PROMPT,
            callbacks=callbacks,
        )

        user_message = (
            f"SSIM score: {ssim:.1f}% (threshold: {threshold}%)\n"
            f"The screenshots differ. Analyze whether this is a meaningful UI change or noise.\n"
            f"Baseline image size: {len(baseline_image)} bytes\n"
            f"Current image size: {len(current_image)} bytes\n"
            f"(Images provided as context — compare the visual differences)"
        )

        try:
            response = conv.ask(user_message)
            return json.loads(response)
        except json.JSONDecodeError:
            return {'verdict': 'needs_review', 'confidence': 0.5, 'summary': response[:500] if response else 'Parse error'}
        except Exception as e:
            return {'verdict': 'needs_review', 'confidence': 0, 'summary': str(e)}

    # -----------------------------------------------------------
    # Regression Report
    # -----------------------------------------------------------

    def generate_regression_report(self, run_id):
        """Generate a regression report summarizing all visual assertions in a run."""
        run = self.get_automation_run(run_id)
        if not run:
            return None

        step_results = run.get('step_results', [])
        visual_results = []
        total_assertions = 0
        passed = 0
        failed = 0
        needs_review = 0

        for idx, sr in enumerate(step_results):
            if sr.get('step_type') != 'screenshot_assert':
                continue
            total_assertions += 1

            # Parse visual result from output/error
            vr_result = {
                'step_index': idx,
                'step_label': sr.get('label', ''),
                'status': sr.get('status', 'unknown'),
                'output': sr.get('output', ''),
                'error': sr.get('error', ''),
            }

            if sr.get('status') == 'completed':
                passed += 1
                vr_result['verdict'] = 'pass'
            elif sr.get('status') == 'failed':
                failed += 1
                vr_result['verdict'] = 'fail'
            else:
                needs_review += 1
                vr_result['verdict'] = 'needs_review'

            visual_results.append(vr_result)

        return {
            'run_id': run_id,
            'automation_id': run.get('automation_id'),
            'automation_name': run.get('automation_name'),
            'device_id': run.get('device_id'),
            'total_assertions': total_assertions,
            'passed': passed,
            'failed': failed,
            'needs_review': needs_review,
            'results': visual_results,
            'generated_at': time.time(),
        }

    # -----------------------------------------------------------
    # Capture baseline from device
    # -----------------------------------------------------------

    def capture_baseline(self, automation_id, step_index, device_id, label=None, mask_regions=None):
        """Capture a screenshot from a device and store it as a baseline."""
        screenshot_data = self.take_screenshot(device_id)
        if not screenshot_data:
            raise Exception(f"Failed to capture screenshot from device {device_id}")

        # Get device info for multi-device baselines
        device_model = 'default'
        resolution = 'default'
        try:
            d = self.get_device(device_id)
            info = d.info
            device_model = info.get('productName', 'default')
            resolution = f"{info.get('displayWidth', 0)}x{info.get('displayHeight', 0)}"
        except Exception:
            pass

        return self.create_baseline(
            automation_id=automation_id,
            step_index=step_index,
            image_data=screenshot_data,
            device_model=device_model,
            resolution=resolution,
            label=label,
            mask_regions=mask_regions,
        )
