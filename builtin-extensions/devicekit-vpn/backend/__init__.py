"""devicekit-vpn — the worked example of an app-driver extension (plan 18).

Owns no host code: it is a thin consumer of the ``devicekit_sdk.appdriver`` framework —
version-keyed adapters for ExpressVPN's connect/disconnect/status flows, an allowed-countries
gate, and a device-side egress verifier. The framework does the provisioning, per-device adapter
resolution, and version-policy enforcement.
"""
