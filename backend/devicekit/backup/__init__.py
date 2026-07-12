"""Backup / DR of DeviceKit's own state (plan 25 part 6).

"A backup you've never restored is an assumption, not a safety net." (ServerKit's
``BACKUP_PROTECTION`` doctrine.) This package delivers:

* ``service`` — tarball + a **separately-stored** ``manifest.json`` (per-artifact sha256, tool
  versions, chain refs);
* ``verify`` — the ladder ``none → listed → hashed`` (hash compared to the *stored* manifest,
  never one recomputed from the same possibly-corrupt tar);
* ``drill`` — restore the latest backup into a **throwaway scratch DB**, probe-verify, tear it
  down in a ``finally`` — never touching live. Hard guards: free-space precheck (loud skip),
  vacuous-drill guard (0 files fails, doesn't earn ``drilled``).
"""
