"""Data model for devicekit-vpn.

The only table is the provisioning ledger, and it is owned by the framework — the extension just
asks for it so the ``ext_devicekit_vpn_provisioned`` table exists (device_id, serial, package,
version_name, sha256, status, provisioned_at). Namespaced under the slug, so ``uninstall --purge``
drops it.
"""
from devicekit_sdk import appdriver

SLUG = "devicekit-vpn"


def register(db):
    """Called at activation. Defines + creates the provisioning table on the shared metadata."""
    appdriver.provisioned_table(SLUG)
