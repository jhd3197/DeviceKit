import requests
import pychrome
import time
import re
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from functools import wraps
from difflib import SequenceMatcher
import urllib.parse

logger = logging.getLogger(__name__)


def with_timeout(timeout_seconds):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(f, *args, **kwargs)
                try:
                    return future.result(timeout=timeout_seconds)
                except TimeoutError:
                    logger.error(f"{f.__name__} timed out after {timeout_seconds}s")
                    raise
        return wrapper
    return decorator


class CdpMixin:
    def normalize_url(self, url):
        url = re.sub(r'^https?://(www\.)?', '', url)
        return url.rstrip('/').lower()

    def get_tab(self, local_port=9222, match_url=None):
        """Get the tab matching the URL."""
        for attempt in range(5):
            try:
                response = requests.get(f"http://127.0.0.1:{local_port}/json")
                response.raise_for_status()
                tabs = response.json()

                if match_url:
                    normalized = self.normalize_url(match_url)
                    for t in tabs:
                        if normalized in self.normalize_url(t.get("url", "")):
                            return t
                    best_score, best_tab = 0.0, None
                    for t in tabs:
                        score = SequenceMatcher(
                            None, normalized, self.normalize_url(t.get("url", ""))
                        ).ratio()
                        if score > best_score:
                            best_score, best_tab = score, t
                    if best_score >= 0.75:
                        return best_tab
                elif tabs:
                    return tabs[0]
            except Exception as e:
                logger.error(f"Error retrieving tabs attempt {attempt + 1}: {e}")
            time.sleep(1)
        raise RuntimeError("Could not find an open Chrome tab.")

    @with_timeout(60 * 10)
    def get_single_tab(self, url, device_id=None, match_url=None):
        """Retrieve a single tab matching criteria."""
        max_retries = 10
        if match_url is None:
            parsed = urllib.parse.urlparse(url)
            match_url = '.'.join(parsed.netloc.split('.')[-2:])

        metadata = self.get_device_vpn_metadata(device_id)
        local_port = metadata.get("port", 9222) if metadata else 9222

        for attempt in range(max_retries):
            self.start_chrome_browser(url, device_id)
            time.sleep(4)
            self.forward_devtools_port(device_id, local_port=local_port)
            time.sleep(4)

            try:
                tab_info = self.get_tab(local_port, match_url=match_url)
                self.browser = pychrome.Browser(url=f"http://127.0.0.1:{local_port}")
                tabs = self.browser.list_tab()
                tab = next((t for t in tabs if t.id == tab_info["id"]), None)
                if not tab:
                    raise RuntimeError("Tab not found")

                tab.start()
                tab.Runtime.enable()
                tab.Page.enable()
                tab.Network.enable()

                wait_start = time.time()
                while time.time() - wait_start < 15:
                    result = self.evaluate_js_expression("document.readyState", tab)
                    if result and result.get('value') == 'complete':
                        return tab
                    time.sleep(1)
                return tab
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                self.close_tab()
                if attempt < max_retries - 1:
                    local_port += 100
                    time.sleep(5)
                else:
                    raise

    def evaluate_js_expression(self, expression, tab):
        try:
            result = tab.Runtime.evaluate(expression=expression, returnByValue=True)
            return result['result']
        except Exception as e:
            logger.error(f"Error evaluating JS: {e}")
            return None

    def wait_for_element(self, expression, tab, timeout=10):
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.evaluate_js_expression(expression, tab)
            if result and result.get('value', False):
                return True
            time.sleep(0.5)
        return False

    def go_to_next_page(self, tab):
        js = """(() => { const b = document.querySelector('#pnnext'); if (b) { b.click(); return true; } return false; })()"""
        result = self.evaluate_js_expression(js, tab)
        if result and result.get('value', False):
            time.sleep(3)
            return True
        return False

    def force_close_chrome_tabs(self, device=None):
        try:
            if self.exists_by_resource_id("com.android.chrome:id/tab_switcher_button", device_id=device):
                self.click_by_resource_id("com.android.chrome:id/tab_switcher_button", device_id=device)
            time.sleep(1)
            if self.exists_by_resource_id("com.android.chrome:id/menu_button_container", device_id=device):
                self.click_by_resource_id("com.android.chrome:id/menu_button_container", device_id=device)
            time.sleep(1)
            for text in ["Close all tabs and groups", "Close all tabs"]:
                if self.exists_by_text(text, device_id=device):
                    self.click_by_text(text, device_id=device)
                    break
            time.sleep(1)
            self.press_action("home", device_id=device)
            return True
        except Exception as e:
            logger.error(f"Error force closing Chrome tabs: {e}")
            return False

    def close_tab(self):
        try:
            self.force_close_chrome_tabs(device=getattr(self, 'device', None))
        except Exception:
            logger.error("Error in ADB tab closing method")

    def wait_for_network_idle(self, tab, timeout=10, max_inflight=0):
        try:
            start_time = time.time()
            inflight = 0

            def on_start(**kwargs):
                nonlocal inflight
                inflight += 1

            def on_finish(**kwargs):
                nonlocal inflight
                inflight = max(0, inflight - 1)

            tab.Network.requestWillBeSent = on_start
            tab.Network.loadingFinished = on_finish
            tab.Network.loadingFailed = on_finish

            while time.time() - start_time < timeout:
                if inflight <= max_inflight:
                    return True
                time.sleep(0.1)
            return False
        except Exception as e:
            logger.error(f"Error in wait_for_network_idle: {e}")
            return False
