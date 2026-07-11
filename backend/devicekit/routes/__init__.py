"""Blueprint modules for the DeviceKit API.

Each module exposes ``make_blueprint(client, limiter) -> Blueprint``. The ``client`` is the
mixin composite (the service layer); handlers call ``client.run_automation(...)`` exactly
as they did when every route was a closure inside ``api_app()``. ``limiter`` is the shared
Flask-Limiter instance, used by the few routes that need per-route rate limits.

``register_all(app, client, limiter)`` mounts every blueprint on the app. URLs are
identical to the pre-refactor closure routes (plan 02); only the code layout changed.
"""
from devicekit.routes import (
    health,
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
    streaming,
    visual_regression,
    fleet_query,
    debug_bundles,
    extensions,
    jobs,
    notifications,
    metrics,
)

# Registration order does not affect URL matching (Flask matches by rule specificity),
# but this mirrors the section order of the original api_app.py for readability.
BLUEPRINT_MODULES = [
    health,
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
    streaming,
    visual_regression,
    fleet_query,
    debug_bundles,
    extensions,
    jobs,
    notifications,
    metrics,
]


def register_all(app, client, limiter):
    """Register every route blueprint on the Flask app."""
    for module in BLUEPRINT_MODULES:
        app.register_blueprint(module.make_blueprint(client, limiter))
