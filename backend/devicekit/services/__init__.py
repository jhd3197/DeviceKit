"""Service layer for DeviceKit's identity/RBAC stack (plan 20).

Unlike the mixins (which are composed onto the ``Client`` god-object and hold request-facing
behavior), these modules are plain functions/dataclasses with no ``self`` — the pure policy
that the identity mixins call into. Ported from ServerKit's ``services/*`` but rewritten in
DeviceKit's idiom (raw ``Base`` models, string-UUID PKs, float-epoch times, session queries).
"""
