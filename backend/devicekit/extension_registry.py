"""Extension registry client (plan 03; port of ServerKit ``registry_service``).

Fetches the curated ``devicekit-extensions`` ``index.json`` with an in-memory TTL cache and
an offline fallback chain: **remote → last-good cache → bundled copy**. Env var semantics
match ServerKit:

* ``DEVICEKIT_REGISTRY_URL`` unset  ⇒ the public registry (``DEFAULT_REGISTRY_URL``).
* set-but-empty                     ⇒ disabled / air-gapped (bundled copy only; also how
  tests stay offline).
* set to a URL                      ⇒ that URL.

``refresh`` never raises — a network failure keeps serving the last good data.
"""
import os
import json
import time
import logging
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_URL = "https://raw.githubusercontent.com/jhd3197/devicekit-extensions/main/index.json"

_BUNDLED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "registry_index.json")

# Fields we surface (with defaults); anything else in an entry is stripped before the UI.
_FIELDS = {
    "slug": None, "display_name": None, "description": "", "version": "0.0.0",
    "category": "utility", "author": "", "first_party": False, "bundled": False,
    "permissions": list, "min_devicekit_version": None, "max_devicekit_version": None,
    # ``requires`` mirrors the manifest ``requires_extensions`` (slug -> version range) so the
    # marketplace can show "requires devicekit-browser" and the installer can offer the chain
    # (plan 17).
    "requires": dict,
    "source": None, "sha256": None, "repo": None, "homepage": None,
    "logo": None, "screenshots": list,
}

# Module-level cache: {"ts": float, "entries": [...], "source": "remote|cache|bundled"}.
_cache = {"ts": 0.0, "entries": None, "source": None}


def get_registry_url():
    """Resolve the configured registry URL. Returns ``None`` when disabled (set-but-empty)."""
    val = os.environ.get("DEVICEKIT_REGISTRY_URL")
    if val is None:
        return DEFAULT_REGISTRY_URL
    val = val.strip()
    return val or None  # empty string ⇒ disabled


def _ttl():
    try:
        return int(os.environ.get("DEVICEKIT_REGISTRY_TTL", "3600"))
    except ValueError:
        return 3600


def _normalize(entry):
    out = {}
    for field, default in _FIELDS.items():
        if callable(default):
            out[field] = entry.get(field, default())
        else:
            out[field] = entry.get(field, default)
    return out


def _load_bundled():
    try:
        with open(_BUNDLED_PATH, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return [_normalize(e) for e in payload.get("extensions", [])]
    except Exception as e:
        logger.warning(f"Bundled registry unreadable: {e}")
        return []


def _fetch_remote(url):
    req = urllib.request.Request(url, headers={"User-Agent": "DeviceKit-Extensions"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — curated source
        payload = json.loads(resp.read())
    return [_normalize(e) for e in payload.get("extensions", [])]


def refresh(force=False):
    """Return the registry entries, refreshing from remote when the cache is stale.

    Never raises: on remote failure, keeps the last-good cache, else falls back to the
    bundled copy. Records where the data came from in ``_cache['source']``.
    """
    now = time.time()
    if not force and _cache["entries"] is not None and (now - _cache["ts"]) < _ttl():
        return _cache["entries"]

    url = get_registry_url()
    if url is None:
        # Disabled / air-gapped — bundled copy only.
        entries = _load_bundled()
        _cache.update(ts=now, entries=entries, source="bundled")
        return entries

    try:
        entries = _fetch_remote(url)
        _cache.update(ts=now, entries=entries, source="remote")
        return entries
    except Exception as e:
        logger.warning(f"Registry fetch failed ({e}); using fallback")
        if _cache["entries"] is not None:
            _cache["source"] = "cache"
            return _cache["entries"]
        entries = _load_bundled()
        _cache.update(ts=now, entries=entries, source="bundled")
        return entries


def list_extensions(force=False):
    return refresh(force=force)


def get_entry(slug, force=False):
    for e in refresh(force=force):
        if e["slug"] == slug:
            return e
    return None


def source_label():
    return _cache.get("source")


def _reset_cache():
    """Testing helper — drop the in-memory cache."""
    _cache.update(ts=0.0, entries=None, source=None)
