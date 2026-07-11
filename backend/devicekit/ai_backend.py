"""AI backend selection — route Prompture through a prompture-hub gateway (plan 19).

DeviceKit has exactly one AI path: Prompture. Which *backend* serves those calls is a
durable setting (``ai.backend``):

- ``direct`` (default): Prompture's built-in drivers, provider keys from the environment
  (pushed there by ``SettingsMixin._apply_provider_keys``). Today's behavior, unchanged.
- ``hub``: every provider prefix in Prompture's driver registry is overridden with a
  factory returning a :class:`HubDriver` — an ``OpenAIDriver`` pointed at the hub's
  OpenAI-compatible ``{ai.hub.url}/v1`` surface, authenticated with the single scoped
  ``ph_...`` hub key. Real provider keys never enter DeviceKit; the hub holds them.

Model ids keep their ``provider/model`` shape end-to-end: Prompture's resolver splits on
the first ``/`` to pick a factory, and our factory re-prepends the prefix so the hub
receives the full id (its ``/v1/models`` lists ids like ``ollama/llama3.1:8b``).

Capability note (validated against prompture-hub v0.0.2 source, logged per plan 19):
the hub's ``/v1/chat/completions`` accepts no ``tools`` or ``response_format`` fields and
flattens messages to plain text, so through the hub Prompture falls back to *simulated*
tool use and prompted-repair structured output, and vision content is unavailable. SSE
streaming IS implemented hub-side. The flags on :class:`HubDriver` encode exactly that,
so Prompture degrades gracefully instead of silently dropping tool calls.
"""
import logging
import threading

import requests

logger = logging.getLogger(__name__)

DEFAULT_HUB_URL = "http://localhost:1984"

# Serialize registry swaps: settings saves can race the boot-time apply.
_apply_lock = threading.Lock()

# Provider prefixes DeviceKit reroutes to the hub. This is the set of LLM prefixes
# Prompture registers as built-ins; anything a user types as ``prefix/model`` in the AI
# settings pane is covered. Kept explicit so switching back to ``direct`` only needs
# ``register_all_builtin_drivers()`` and no bookkeeping of what we replaced.
_HUB_PREFIXES = None  # resolved lazily from Prompture's live registry


def _hub_driver_class():
    from prompture.drivers.openai_driver import OpenAIDriver

    class HubDriver(OpenAIDriver):
        """OpenAIDriver aimed at prompture-hub. Honest capability flags: the hub's
        v0.0.x chat endpoint has no native tool-calling / json-schema / vision, but
        does stream."""
        supports_tool_use = False
        supports_streaming_tool_use = False
        supports_json_mode = False
        supports_json_schema = False
        supports_vision = False
        supports_streaming = True

    return HubDriver


def _make_hub_factory(driver_cls, prefix, base_url, hub_key):
    def factory(model=None):
        if not hub_key:
            raise ValueError(
                "AI backend is 'hub' but no hub key is configured — set ai.hub.key "
                "in Settings → AI (create one on the hub dashboard)."
            )
        full_model = f"{prefix}/{model}" if model else prefix
        return driver_cls(api_key=hub_key, model=full_model, base_url=base_url)
    return factory


def hub_base_url(hub_url):
    """Normalize a configured hub URL to its OpenAI-compatible /v1 base."""
    url = (hub_url or DEFAULT_HUB_URL).rstrip("/")
    return f"{url}/v1"


def apply_ai_backend(backend, hub_url=None, hub_key=None):
    """(Re)configure Prompture's driver registry for the chosen backend. Idempotent —
    called at boot and on every AI settings save. Existing Conversations keep their
    already-built driver; new ones pick up the change."""
    from prompture import register_driver
    from prompture.drivers.provider_descriptors import register_all_builtin_drivers
    from prompture.drivers.registry import list_registered_drivers

    with _apply_lock:
        # Restore the pristine built-in registry first so hub→direct and repeated
        # hub applies (e.g. a URL change) both start from a known state.
        register_all_builtin_drivers()

        if backend != "hub":
            logger.info("AI backend: direct (Prompture built-in drivers)")
            return "direct"

        base_url = hub_base_url(hub_url)
        driver_cls = _hub_driver_class()
        prefixes = list_registered_drivers()
        for prefix in prefixes:
            register_driver(
                prefix,
                _make_hub_factory(driver_cls, prefix, base_url, hub_key),
                overwrite=True,
            )
        logger.info(
            f"AI backend: hub — {len(prefixes)} provider prefixes routed to {base_url} "
            f"(key {'set' if hub_key else 'MISSING'}; native tool-use/json-schema "
            f"degrade to Prompture's simulated/prompted fallbacks through the hub)"
        )
        return "hub"


def probe_hub(hub_url, hub_key=None, timeout=3.0, models_timeout=15.0):
    """Probe a prompture-hub instance: ``GET /health`` for liveness, then ``GET
    /v1/models`` (key-scoped) for the allowed-model list. Never raises — the Settings
    pane renders whatever this reports, reachable or not. The model list gets a longer
    timeout: the hub builds its catalog lazily, so the first call after hub boot can
    take several seconds while later ones are instant."""
    url = (hub_url or DEFAULT_HUB_URL).rstrip("/")
    result = {
        "url": url,
        "reachable": False,
        "key_set": bool(hub_key),
        "models": [],
        "models_error": None,
        "error": None,
    }

    try:
        resp = requests.get(f"{url}/health", timeout=timeout)
        if resp.status_code == 200:
            result["reachable"] = True
        else:
            result["error"] = f"hub /health returned {resp.status_code}"
            return result
    except requests.RequestException as e:
        result["error"] = f"hub not reachable at {url}: {e.__class__.__name__}"
        return result

    if not hub_key:
        result["models_error"] = "no hub key configured"
        return result

    try:
        resp = requests.get(
            f"{url}/v1/models",
            headers={"Authorization": f"Bearer {hub_key}"},
            timeout=models_timeout,
        )
        if resp.status_code == 200:
            data = resp.json().get("data") or []
            result["models"] = sorted(m.get("id") for m in data if m.get("id"))
        elif resp.status_code == 401:
            result["models_error"] = "hub key rejected (401) — create a new key on the hub dashboard"
        else:
            result["models_error"] = f"hub /v1/models returned {resp.status_code}"
    except requests.RequestException as e:
        result["models_error"] = f"model list failed: {e.__class__.__name__}"
    except ValueError:
        result["models_error"] = "hub /v1/models returned invalid JSON"

    return result
