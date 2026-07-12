"""The agent trust boundary: a fixed allowlist of read-only survey primitives (plan 25).

ServerKit's ``AGENT_SURVEY_SPEC`` lesson, ported for Android: the device enforces a
**fixed set of read-only primitives**; the server (and the untrusted panel above it) may
only *combine* them into health/actions. The server can never name a raw shell command,
and no primitive ever returns whole-file contents — env/secret files are listed **by path
only, never read**. This is the boundary the plan-24 doctor probes assume.

This module is pure data + validation (no device, no I/O) so it is trivially testable and
shared by both the composing side (``AgentSurveyMixin``) and any conformant agent that
wants to publish the same catalog. The agent's on-device dispatcher enforces the *same*
allowlist — the server-side check here is defense in depth, not the only gate.
"""

# Argument spec: {name: {"type": <py type name>, "required": bool, "default": <value>}}.
# Every primitive is read-only and returns metadata / lists — never file contents. That
# invariant is asserted at import time below.
PRIMITIVES = {
    "file.exists": {
        "description": "Test whether a path exists on the device. Metadata only — never "
                       "returns contents, so env/secret files are safe to probe.",
        "args": {"path": {"type": "str", "required": True}},
        "returns": "exists (bool)",
    },
    "file.stat": {
        "description": "Path metadata: size, mtime, is_dir, mode. Never returns contents; "
                       "this is how a secret file is 'listed by path only'.",
        "args": {"path": {"type": "str", "required": True}},
        "returns": "size, mtime, is_dir, mode",
    },
    "fs.glob": {
        "description": "List paths matching a glob (paths only, count-capped). Returns "
                       "names, never contents.",
        "args": {
            "pattern": {"type": "str", "required": True},
            "limit": {"type": "int", "required": False, "default": 500},
        },
        "returns": "matches ([path])",
    },
    "app.status": {
        "description": "Installed/running state + versionName for a single package "
                       "(the 'unit/app status' primitive).",
        "args": {"package": {"type": "str", "required": True}},
        "returns": "installed, running, version",
    },
    "app.list": {
        "description": "Installed packages with versionName (the package/version list). "
                       "No file contents.",
        "args": {"include_system": {"type": "bool", "required": False, "default": False}},
        "returns": "packages ([{package, version}])",
    },
    "process.list": {
        "description": "Running processes (pid, name). No contents.",
        "args": {},
        "returns": "processes ([{pid, name}])",
    },
    "metrics.snapshot": {
        "description": "Current device metrics: cpu, ram, battery, temperature, network, "
                       "storage.",
        "args": {},
        "returns": "cpu, ram, battery, temperature, network, storage",
    },
}

# Named server-side recipes: an ordered list of primitive invocations the composer runs and
# combines. A probe is JUST a list of allowlisted primitives — it can never smuggle a raw
# command, because every step is validated against PRIMITIVES before dispatch.
AGENT_PACKAGE = "com.devicekit.agent"
COMPOSED_PROBES = {
    "health": [
        {"primitive": "metrics.snapshot", "args": {}},
        {"primitive": "app.status", "args": {"package": AGENT_PACKAGE}},
    ],
    "agent_alive": [
        {"primitive": "app.status", "args": {"package": AGENT_PACKAGE}},
    ],
    "storage": [
        {"primitive": "metrics.snapshot", "args": {}},
    ],
    "inventory": [
        {"primitive": "app.list", "args": {"include_system": False}},
        {"primitive": "process.list", "args": {}},
    ],
}

_PY_TYPES = {"str": str, "int": int, "bool": bool, "float": (int, float)}


class PrimitiveError(ValueError):
    """Raised when a caller names a primitive outside the allowlist or gives bad args.

    The message deliberately never echoes back the rejected command verbatim into a shell —
    the whole point of the boundary is that unknown names are refused, not run.
    """


def is_primitive(name):
    return name in PRIMITIVES


def list_primitives():
    """The public catalog (for ``GET /agent-device/primitives`` and agent publication)."""
    return {
        "primitives": {
            name: {"description": spec["description"],
                   "args": spec["args"],
                   "returns": spec["returns"],
                   "read_only": True}
            for name, spec in PRIMITIVES.items()
        },
        "probes": {name: [s["primitive"] for s in steps]
                   for name, steps in COMPOSED_PROBES.items()},
    }


def validate_primitive(name, args):
    """Validate a primitive call and return a normalized args dict.

    Raises ``PrimitiveError`` if ``name`` is not on the allowlist (the trust boundary), if a
    required arg is missing, or if an arg has the wrong type. Unknown args are dropped rather
    than passed through, so the composer can never widen a primitive's contract.
    """
    spec = PRIMITIVES.get(name)
    if spec is None:
        raise PrimitiveError(
            f"'{name}' is not an allowlisted read-only primitive; the server may only "
            f"compose the fixed survey set, never name a raw command")
    args = args or {}
    if not isinstance(args, dict):
        raise PrimitiveError(f"args for '{name}' must be an object")
    out = {}
    for arg_name, arg_spec in spec["args"].items():
        if arg_name in args and args[arg_name] is not None:
            value = args[arg_name]
            expected = _PY_TYPES[arg_spec["type"]]
            # bool is an int subclass — reject an accidental bool where an int is wanted.
            if arg_spec["type"] == "int" and isinstance(value, bool):
                raise PrimitiveError(f"arg '{arg_name}' of '{name}' must be an int")
            if not isinstance(value, expected):
                raise PrimitiveError(
                    f"arg '{arg_name}' of '{name}' must be {arg_spec['type']}")
            out[arg_name] = value
        elif arg_spec["required"]:
            raise PrimitiveError(f"primitive '{name}' requires arg '{arg_name}'")
        elif "default" in arg_spec:
            out[arg_name] = arg_spec["default"]
    return out


def get_probe(name):
    """Return the (validated) recipe for a composed probe, or raise ``PrimitiveError``.

    Validates every step up front so a malformed catalog fails loudly rather than at
    dispatch time, and so callers are guaranteed the recipe only names allowlisted
    primitives.
    """
    recipe = COMPOSED_PROBES.get(name)
    if recipe is None:
        raise PrimitiveError(f"unknown probe '{name}'")
    return [{"primitive": s["primitive"],
             "args": validate_primitive(s["primitive"], s.get("args") or {})}
            for s in recipe]


def _assert_invariants():
    """Fail import if the catalog ever grows a write/exfiltration primitive.

    These names are what a shell-command or whole-file-read primitive would be called; the
    allowlist must never contain them. This is a guardrail against a future edit quietly
    reopening the trust boundary.
    """
    forbidden = {"shell", "exec", "run", "cmd", "file.read", "file.pull", "cat",
                 "pull", "download", "read", "eval", "su"}
    leaked = forbidden & set(PRIMITIVES)
    assert not leaked, f"allowlist leaked non-read-only primitive(s): {leaked}"
    for name, steps in COMPOSED_PROBES.items():
        for step in steps:
            assert step["primitive"] in PRIMITIVES, \
                f"probe '{name}' names non-allowlisted primitive '{step['primitive']}'"


_assert_invariants()
