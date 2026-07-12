"""Blueprint modules for the DeviceKit API.

Each module exposes ``make_blueprint(client, limiter) -> Blueprint``. The ``client`` is the
mixin composite (the service layer); handlers call ``client.run_automation(...)`` exactly
as they did when every route was a closure inside ``api_app()``. ``limiter`` is the shared
Flask-Limiter instance, used by the few routes that need per-route rate limits.

``register_all(app, client, limiter)`` mounts every blueprint on the app. URLs are
identical to the pre-refactor closure routes (plan 02); only the code layout changed.
Every blueprint is additionally mirrored under ``/api/v1`` (plan 21) — same handlers,
same auth gate (which version-strips paths), so one endpoint serves the UI and machines.
"""
from devicekit.services.scopes import API_V1_PREFIX
from devicekit.routes import (
    api_v1,
    actions,
    health,
    auth,
    api_keys,
    audit,
    workspaces,
    vault,
    events,
    devices,
    dashboard,
    device_control,
    pipeline,
    queue,
    alerts,
    activity,
    config,
    settings,
    automations,
    profiles,
    fleet,
    ai_agent,
    agent_devices,
    agent_ota,
    onboarding,
    agent_plugins,
    backups,
    streaming,
    visual_regression,
    fleet_query,
    fleet_policies,
    debug_bundles,
    extensions,
    jobs,
    notifications,
    metrics,
)

# Registration order does not affect URL matching (Flask matches by rule specificity),
# but this mirrors the section order of the original api_app.py for readability.
BLUEPRINT_MODULES = [
    api_v1,
    actions,
    health,
    auth,
    api_keys,
    audit,
    workspaces,
    vault,
    events,
    devices,
    dashboard,
    device_control,
    pipeline,
    queue,
    alerts,
    activity,
    config,
    settings,
    automations,
    profiles,
    fleet,
    ai_agent,
    agent_devices,
    agent_ota,
    onboarding,
    agent_plugins,
    backups,
    streaming,
    visual_regression,
    fleet_query,
    fleet_policies,
    debug_bundles,
    extensions,
    jobs,
    notifications,
    metrics,
]


def register_all(app, client, limiter):
    """Register every route blueprint on the Flask app, plus the ``/api/v1`` mirror.

    The mirror registers a *fresh* blueprint instance per module (Flask forbids reusing
    one) under a ``v1_`` name and the version prefix. ``api_v1`` itself is skipped — its
    rules already carry the absolute ``/api/v1`` prefix."""
    for module in BLUEPRINT_MODULES:
        app.register_blueprint(module.make_blueprint(client, limiter))
    for module in BLUEPRINT_MODULES:
        if module is api_v1:
            continue
        bp = module.make_blueprint(client, limiter)
        app.register_blueprint(bp, url_prefix=API_V1_PREFIX, name=f"v1_{bp.name}")
