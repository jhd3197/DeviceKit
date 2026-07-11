"""A small Chrome DevTools Protocol client.

The only wire dependency is ``websocket-client`` (declared in the backend requirements — this
is a builtin, so it does not ride the ``DEVICEKIT_ALLOW_EXTENSION_PIP`` gate). Target discovery
is plain HTTP (``GET http://127.0.0.1:<port>/json``); commands go over the per-target
WebSocket. Connections are opened per operation and closed immediately — one CDP client per
target, no shared long-lived socket (Flask is threaded).

Each session owns a **dedicated** tab created via ``Target.createTarget`` and pinned by its
``targetId``. That matters on Android: Chrome freezes *background* tabs, so driving an
arbitrary pre-existing tab hangs; a dedicated tab we activate stays responsive. Every op
brings the tab to front before acting. Chrome 111+ rejects CDP handshakes carrying a
disallowed ``Origin`` header, so the socket is opened with ``suppress_origin=True``.
"""
import json
import time
import base64
import itertools

import requests
import websocket  # websocket-client

import devicekit_sdk

SLUG = "devicekit-browser"
log = devicekit_sdk.logger(SLUG)

CHROME_PACKAGE = "com.android.chrome"


class CDPError(Exception):
    """A CDP command failed, the target was unreachable, or Chrome is not available."""


# --------------------------------------------------------------------------- HTTP discovery
def list_targets(port, timeout=5):
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/json", timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise CDPError(f"Chrome DevTools not reachable on port {port}: {e}")


def browser_ws(port, timeout=5):
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=timeout)
        resp.raise_for_status()
        url = resp.json().get("webSocketDebuggerUrl")
    except Exception as e:
        raise CDPError(f"Chrome DevTools not reachable on port {port}: {e}")
    if not url:
        raise CDPError("Chrome exposed no browser WebSocket endpoint")
    return url


def page_ws_url(port, target_id):
    return f"ws://127.0.0.1:{port}/devtools/page/{target_id}"


def target_exists(port, target_id):
    if not target_id:
        return False
    try:
        return any(t.get("id") == target_id for t in list_targets(port))
    except CDPError:
        return False


# --------------------------------------------------------------------------- connection
class CDPConnection:
    """A short-lived synchronous CDP connection to one target's WebSocket. Use as a context
    manager. ``send`` correlates responses by id and buffers interleaved events."""

    def __init__(self, ws_url, timeout=30):
        try:
            self._ws = websocket.create_connection(
                ws_url, timeout=timeout, max_size=None, suppress_origin=True)
        except Exception as e:
            raise CDPError(f"Could not connect to CDP target: {e}")
        self._ids = itertools.count(1)
        self._timeout = timeout
        self._events = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def send(self, method, params=None, timeout=None):
        mid = next(self._ids)
        self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + (timeout or self._timeout)
        while time.time() < deadline:
            self._ws.settimeout(max(0.1, deadline - time.time()))
            try:
                raw = self._ws.recv()
            except websocket.WebSocketTimeoutException:
                break
            except Exception as e:
                raise CDPError(f"CDP connection dropped during {method}: {e}")
            if not raw:
                continue
            msg = json.loads(raw)
            if msg.get("id") == mid:
                if "error" in msg:
                    raise CDPError(msg["error"].get("message", f"{method} failed"))
                return msg.get("result", {})
            if "method" in msg:
                self._events.append(msg)
        raise CDPError(f"Timed out waiting for {method} response")

    def close(self):
        try:
            self._ws.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- browser-level
def create_target(port, url="about:blank", timeout=15):
    """Create a dedicated tab and return its targetId."""
    conn = CDPConnection(browser_ws(port, timeout=timeout), timeout=timeout)
    with conn:
        r = conn.send("Target.createTarget", {"url": url}, timeout=timeout)
        tid = r.get("targetId")
        if not tid:
            raise CDPError("Target.createTarget returned no targetId")
        try:
            conn.send("Target.activateTarget", {"targetId": tid}, timeout=timeout)
        except CDPError:
            pass
        return tid


def close_target(port, target_id, timeout=5):
    if not target_id:
        return
    try:
        conn = CDPConnection(browser_ws(port, timeout=timeout), timeout=timeout)
        with conn:
            conn.send("Target.closeTarget", {"targetId": target_id}, timeout=timeout)
    except CDPError:
        pass


# --------------------------------------------------------------------------- page ops
def _connect_page(port, target_id, timeout=30):
    conn = CDPConnection(page_ws_url(port, target_id), timeout=timeout)
    try:
        conn.send("Page.bringToFront", timeout=min(timeout, 5))
    except CDPError:
        pass  # best-effort — keep the tab foreground/un-frozen on Android
    return conn


def navigate(port, target_id, url, timeout=30):
    """Navigate the pinned tab to ``url`` and wait for load. Returns the resolved URL."""
    conn = _connect_page(port, target_id, timeout=timeout)
    with conn:
        conn.send("Page.enable")
        conn.send("Page.navigate", {"url": url})
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = conn.send("Runtime.evaluate",
                          {"expression": "document.readyState", "returnByValue": True})
            if (r.get("result") or {}).get("value") == "complete":
                break
            time.sleep(0.3)
        cur = conn.send("Runtime.evaluate",
                        {"expression": "document.location.href", "returnByValue": True})
        return (cur.get("result") or {}).get("value", url)


def evaluate(port, target_id, expression, timeout=30):
    conn = _connect_page(port, target_id, timeout=timeout)
    with conn:
        r = conn.send("Runtime.evaluate",
                      {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if r.get("exceptionDetails"):
            raise CDPError(str(r["exceptionDetails"].get("text", "evaluation error")))
        return (r.get("result") or {}).get("value")


_CONTENT_JS = {
    "html": "document.documentElement.outerHTML",
    "text": "document.body ? document.body.innerText : ''",
    "title": "document.title",
    "url": "document.location.href",
}


def content(port, target_id, fmt="html", timeout=30):
    expr = _CONTENT_JS.get(fmt)
    if expr is None:
        raise CDPError(f"unknown content format {fmt!r} (html|text|title|url)")
    return evaluate(port, target_id, expr, timeout=timeout)


def screenshot(port, target_id, full_page=False, timeout=30):
    """Capture a screenshot; returns raw PNG bytes. ``full_page`` uses CDP beyond-viewport
    capture (impossible with adb screencap)."""
    conn = _connect_page(port, target_id, timeout=timeout)
    with conn:
        conn.send("Page.enable")
        params = {"format": "png"}
        if full_page:
            params["captureBeyondViewport"] = True
        r = conn.send("Page.captureScreenshot", params, timeout=timeout)
        data = r.get("data")
        if not data:
            raise CDPError("empty screenshot")
        return base64.b64decode(data)


def tabs(port, timeout=5):
    """List open targets (tabs) as ``{id, type, title, url}``."""
    return [
        {"id": t.get("id"), "type": t.get("type"), "title": t.get("title"), "url": t.get("url")}
        for t in list_targets(port, timeout=timeout)
    ]
