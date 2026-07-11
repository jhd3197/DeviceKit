"""Extension platform — install pipeline, hot-load, status guard, boot loader (plan 03).

A faithful port of ServerKit's ``plugin_service`` adapted to DeviceKit:

* DeviceKit is single-process and uses short-lived ``session_scope`` sessions (no
  Flask-SQLAlchemy global), so the installed-extension row is the authoritative state and
  the in-memory ``self._extensions`` map is a convenience cache.
* Backends extract to ``devicekit/extensions/<slug>/`` and import as
  ``devicekit.extensions.<slug>.<module>``.
* Flask 3 forbids ``register_blueprint`` after the first request, so runtime installs
  briefly clear ``app._got_first_request`` around registration (``_register_ext_blueprint``).
* Safety posture (ServerKit ADR 0002): Zip-Slip guard on every entry, sha256 pin
  (case-insensitive, pre-extraction hard fail), pip gated behind
  ``DEVICEKIT_ALLOW_EXTENSION_PIP``, per-blueprint status guard returning 503 when the row
  is not ``active``. This is not a sandbox — extensions run in-process.
"""
import io
import os
import json
import time
import shutil
import hashlib
import logging
import zipfile
import importlib
import subprocess

from devicekit.db import session_scope, get_engine
from devicekit.models import InstalledExtension
from devicekit.models.extension import STATUS_ACTIVE, STATUS_DISABLED, STATUS_ERROR
from devicekit.extension_manifest import (
    validate_manifest, safe_extract_path, assert_devicekit_compatible, table_prefix,
    range_satisfies,
)

logger = logging.getLogger(__name__)

# Frontend SDK contract version. Extensions import shared UI/primitives from the
# ``devicekit-sdk`` Vite alias (plan 04); this version is the compatibility contract and is
# mirrored in ``frontend/src/extensions/sdk/index.js`` (asserted equal by
# ``tests/test_sdk_version.py``). Bump only on a breaking change to the SDK surface.
SDK_VERSION = "1.0.0"

# Contribution kinds merged into the frontend envelope (plan 04). Order mirrors the plan's
# rendering table; ``page_titles`` is a dict (path -> title) rather than a list.
_LIST_CONTRIB_KINDS = ("nav", "routes", "widgets", "command_palette")

# devicekit/extensions/ — where backend halves are extracted.
_EXTENSIONS_PKG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extensions")
_EXTENSIONS_PKG_DIR = os.path.normpath(_EXTENSIONS_PKG_DIR)

# builtin-extensions/ at the repo root — self-heal / builtin source (plan 04).
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)
BUILTIN_EXTENSIONS_DIR = os.environ.get(
    "DEVICEKIT_BUILTIN_EXTENSIONS_DIR", os.path.join(_REPO_ROOT, "builtin-extensions"))

# Dev-junk skipped when zipping a local working tree for install-local.
_SKIP_DIRS = {".git", ".github", "node_modules", "__pycache__", ".venv", "venv",
              "dist", "build", ".pytest_cache", ".idea", ".vscode"}
_SKIP_FILE_SUFFIXES = (".pyc", ".pyo")


class ExtensionsMixin:
    """Installable extensions: manifest-driven backends hot-loaded into the running app."""

    def init_extensions(self):
        """Initialize in-memory registries and wire the SDK host. Blueprint loading happens
        later, in ``build_app`` (``load_all_extensions``), once the Flask app exists."""
        if not hasattr(self, "_extensions"):
            self._extensions = {}          # slug -> {manifest, status, url_prefix, bp_name}
        self._ext_bp_seq = getattr(self, "_ext_bp_seq", 0)
        # slug -> {'step_types': set, 'fql_fields': set} — names to deregister on teardown.
        if not hasattr(self, "_ext_contributions"):
            self._ext_contributions = {}
        # slug -> [(tool_name, func, description, is_write)] — extension AI tools
        # (bound per-device; write tools are always gated, plan 13).
        if not hasattr(self, "_ext_ai_tools"):
            self._ext_ai_tools = {}
        # slug -> {method_name: callable} — the sibling-callable surface an extension exposes
        # via its ``provides`` register func, dispatched by sdk.extension(slug) (plan 17).
        if not hasattr(self, "_ext_extension_api"):
            self._ext_extension_api = {}
        os.makedirs(_EXTENSIONS_PKG_DIR, exist_ok=True)

        # Let the SDK façade route extension calls back to this live host.
        import devicekit_sdk
        devicekit_sdk.set_host(self)

    # ------------------------------------------------------------------
    # Contribution tracking (called by the SDK register_* helpers)
    # ------------------------------------------------------------------
    def _track_contribution(self, slug, kind, name):
        self._ext_contributions.setdefault(slug, {}).setdefault(kind, set()).add(name)

    def _register_ai_tool(self, slug, name, func, description, is_write=True):
        self._ext_ai_tools.setdefault(slug, []).append((name, func, description, is_write))

    # ------------------------------------------------------------------
    # Sibling-callable API surface (sdk.extension / sdk.provides — plan 17)
    # ------------------------------------------------------------------
    def _register_extension_api(self, slug, name, func):
        """Record a callable an extension exposes to siblings via its ``provides`` func."""
        self._ext_extension_api.setdefault(slug, {})[name] = func

    def invoke_extension_api(self, slug, name, args=(), kwargs=None):
        """Dispatch ``sdk.extension(slug).<name>(*args, **kwargs)`` in-process. Raises
        :class:`devicekit_sdk.ExtensionUnavailable` if the sibling is not installed or not
        active (so a runtime disable degrades a dependent cleanly), and ``AttributeError`` if
        the method isn't part of the sibling's provided surface."""
        import devicekit_sdk
        kwargs = kwargs or {}
        row = self.get_extension(slug)
        if not row:
            raise devicekit_sdk.ExtensionUnavailable(
                f"extension '{slug}' is not installed")
        if row.get("status") != STATUS_ACTIVE:
            raise devicekit_sdk.ExtensionUnavailable(
                f"extension '{slug}' is not active (status: {row.get('status')})")
        func = (self._ext_extension_api.get(slug) or {}).get(name)
        if func is None:
            raise AttributeError(f"extension '{slug}' provides no method '{name}'")
        return func(*args, **kwargs)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def list_extensions(self):
        with session_scope() as s:
            return [e.to_dict() for e in s.query(InstalledExtension).all()]

    def get_extension(self, slug):
        with session_scope() as s:
            e = s.get(InstalledExtension, slug)
            return e.to_dict() if e else None

    def get_contributions_envelope(self):
        """Merge every **active** extension's manifest ``contributions`` block into one
        envelope the React app renders (plan 04). Each entry is tagged with its ``slug`` so
        the frontend resolves the component from the right extension module and scopes a
        per-extension error boundary. Core-vs-extension id collisions are resolved on the
        frontend (core wins); here we only merge extensions. ``page_titles`` is a flat
        ``path -> title`` map; later extensions win a path collision (deterministic by the
        DB's slug order)."""
        envelope = {k: [] for k in _LIST_CONTRIB_KINDS}
        envelope["page_titles"] = {}
        envelope["sdk_version"] = SDK_VERSION
        for ext in self.list_extensions():
            if ext.get("status") != STATUS_ACTIVE:
                continue
            slug = ext["slug"]
            contribs = (ext.get("manifest") or {}).get("contributions") or {}
            for kind in _LIST_CONTRIB_KINDS:
                for entry in contribs.get(kind) or []:
                    if isinstance(entry, dict):
                        envelope[kind].append({**entry, "slug": slug})
            for path, title in (contribs.get("page_titles") or {}).items():
                envelope["page_titles"][path] = title
        return envelope

    def get_extension_config(self, slug):
        with session_scope() as s:
            e = s.get(InstalledExtension, slug)
            if not e:
                return None
            return e.to_dict()["config"]  # secrets already masked

    def get_extension_config_raw(self, slug):
        """Unmasked config for in-process use by the extension itself (via the SDK). Never
        served over the API — that path masks secrets."""
        with session_scope() as s:
            e = s.get(InstalledExtension, slug)
            return dict(e.config or {}) if e else {}

    def update_extension_config(self, slug, updates):
        with session_scope() as s:
            e = s.get(InstalledExtension, slug)
            if not e:
                return None
            cfg = dict(e.config or {})
            cfg.update(updates or {})
            e.config = cfg
            e.updated_at = time.time()
            s.flush()
            return e.to_dict()["config"]

    # ------------------------------------------------------------------
    # Dependency graph (requires_extensions — plan 17)
    # ------------------------------------------------------------------
    def missing_required_extensions(self, manifest):
        """Return a list of unmet dependency problems for ``manifest`` — one per required
        sibling that is not installed or whose installed version is out of range. Empty list
        means every dependency is satisfied. Read-only; used by both preview and the install
        gate so the consent UI and the hard failure agree."""
        requires = manifest.get("requires_extensions") or {}
        if not isinstance(requires, dict):
            return []
        problems = []
        for dep_slug, dep_range in requires.items():
            dep = self.get_extension(dep_slug)
            if not dep:
                problems.append(
                    f"requires '{dep_slug}' ({dep_range or 'any'}), which is not installed — "
                    f"install {dep_slug} first")
            elif not range_satisfies(dep["version"], dep_range):
                problems.append(
                    f"requires '{dep_slug}' {dep_range}, but v{dep['version']} is installed")
        return problems

    def assert_required_extensions(self, manifest):
        """Refuse install when a ``requires_extensions`` dependency is missing or version-
        incompatible. Mirrors :func:`assert_devicekit_compatible`, one level down
        (extension→extension instead of extension→host)."""
        problems = self.missing_required_extensions(manifest)
        if problems:
            name = manifest.get("display_name") or manifest.get("name")
            raise ValueError(f"{name} " + "; ".join(problems) + ".")

    def active_dependents(self, slug):
        """Slugs of currently-active extensions that declare ``slug`` in their
        ``requires_extensions`` — i.e. who would break if ``slug`` went away."""
        dependents = []
        for ext in self.list_extensions():
            if ext["slug"] == slug or ext.get("status") != STATUS_ACTIVE:
                continue
            requires = (ext.get("manifest") or {}).get("requires_extensions") or {}
            if isinstance(requires, dict) and slug in requires:
                dependents.append(ext["slug"])
        return dependents

    # ------------------------------------------------------------------
    # Preview (consent flow) — resolves sha256 without installing
    # ------------------------------------------------------------------
    def preview_extension(self, *, url=None, path=None, zip_bytes=None):
        """Resolve a source to its manifest + pinned sha256 without installing. Powers the
        consent UI; the install pins this sha256 so installed bytes == previewed bytes."""
        buf, source_url = self._resolve_source(url=url, path=path, zip_bytes=zip_bytes)
        digest = hashlib.sha256(buf.getvalue()).hexdigest()
        manifest, _prefix = self._read_manifest(buf)
        validate_manifest(manifest)
        warnings = []
        try:
            assert_devicekit_compatible(manifest)
        except Exception as e:
            warnings.append(str(e))
        existing = self.get_extension(manifest["name"])
        if existing:
            warnings.append(f"'{manifest['name']}' is already installed (v{existing['version']}).")
        # Surface unmet extension dependencies as warnings so the consent UI can offer to
        # install the chain (the actual install still hard-fails on them via the gate).
        warnings.extend(self.missing_required_extensions(manifest))
        # Surface an app-driver's device requirement up front (plan 18): the extension will drive
        # (and, for user_supplied_apk, install) a third-party app — no surprise device changes.
        device_reqs = manifest.get("device_requirements") or {}
        if device_reqs.get("package"):
            pkg = device_reqs["package"]
            if device_reqs.get("provision", "user_supplied_apk") == "user_supplied_apk":
                warnings.append(
                    f"This extension drives {pkg}; you must supply its APK (installed "
                    f"hash-pinned onto each device).")
            else:
                warnings.append(f"This extension drives {pkg} (installed via the Play Store).")
        return {
            "slug": manifest["name"],
            "display_name": manifest.get("display_name", manifest["name"]),
            "version": manifest["version"],
            "category": manifest.get("category", "utility"),
            "description": manifest.get("description", ""),
            "permissions": manifest.get("permissions", []),
            "contributions": manifest.get("contributions", {}),
            "config_schema": manifest.get("config_schema", {}),
            "requires_extensions": manifest.get("requires_extensions", {}),
            "device_requirements": device_reqs,
            "source_url": source_url,
            "sha256": digest,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Install entry points
    # ------------------------------------------------------------------
    def install_extension_from_url(self, url, *, expected_sha256=None, force=False, source="url"):
        buf, source_url = self._resolve_source(url=url)
        if expected_sha256:
            self._verify_sha256(buf, expected_sha256)
        return self._install_from_buffer(buf, source=source, source_url=source_url, force=force)

    def install_extension_from_path(self, path, *, force=False, source="local"):
        buf, source_url = self._resolve_source(path=path)
        return self._install_from_buffer(buf, source=source, source_url=source_url, force=force)

    def install_extension_from_zip(self, zip_bytes, *, force=False, source="upload"):
        buf, source_url = self._resolve_source(zip_bytes=zip_bytes)
        return self._install_from_buffer(buf, source=source, source_url=source_url, force=force)

    def install_builtin_extension(self, slug, *, force=True):
        path = os.path.join(BUILTIN_EXTENSIONS_DIR, slug)
        if not os.path.isdir(path):
            raise ValueError(f"Builtin extension '{slug}' not found at {path}")
        buf, source_url = self._resolve_source(path=path)
        return self._install_from_buffer(buf, source="builtin", source_url=slug, force=force)

    # ------------------------------------------------------------------
    # Registry (marketplace) — browse / install / updates
    # ------------------------------------------------------------------
    def get_extension_registry(self, force=False):
        """Registry entries enriched with each extension's local install state."""
        from devicekit import extension_registry
        entries = extension_registry.list_extensions(force=force)
        installed = {e["slug"]: e for e in self.list_extensions()}
        catalog = []
        for entry in entries:
            local = installed.get(entry["slug"])
            catalog.append({
                **entry,
                "installed": local is not None,
                "installed_version": local["version"] if local else None,
                "status": local["status"] if local else None,
            })
        return {
            "extensions": catalog,
            "count": len(catalog),
            "source": extension_registry.source_label(),
        }

    def install_extension_from_registry(self, slug, *, force=False, install_deps=True):
        """Install a registry entry: bundled entries come from ``builtin-extensions/``,
        others download from the entry's pinned ``source`` + ``sha256``.

        With ``install_deps`` (default), any required siblings the entry declares (registry
        ``requires`` → manifest ``requires_extensions``) that aren't already present+compatible
        are installed first from the registry — the "install the chain" UX (plan 17). The
        install-time gate still enforces the requirement, so a dep that can't be resolved from
        the registry produces the same clear "install X first" error."""
        from devicekit import extension_registry
        entry = extension_registry.get_entry(slug)
        if not entry:
            raise ValueError(f"Extension '{slug}' not found in registry")
        assert_devicekit_compatible({
            "name": entry["slug"], "display_name": entry.get("display_name", entry["slug"]),
            "version": entry["version"],
            "min_devicekit_version": entry.get("min_devicekit_version"),
            "max_devicekit_version": entry.get("max_devicekit_version"),
        })
        if install_deps:
            self._install_required_chain(entry, force=force, _seen=set())
        if entry.get("bundled"):
            return self.install_builtin_extension(slug, force=force or True)
        if not entry.get("source"):
            raise ValueError(f"Registry entry '{slug}' has no source URL")
        return self.install_extension_from_url(
            entry["source"], expected_sha256=entry.get("sha256"),
            force=force, source="registry")

    def _install_required_chain(self, entry, *, force, _seen):
        """Install (from the registry) every required sibling of ``entry`` that isn't already
        present+compatible — depth-first so transitive deps land first. Cycle-guarded by
        ``_seen``; a dep absent from the registry is left for the install gate to report."""
        from devicekit import extension_registry
        requires = entry.get("requires")
        if not isinstance(requires, dict):
            return
        for dep_slug, dep_range in requires.items():
            if dep_slug in _seen:
                continue
            _seen.add(dep_slug)
            current = self.get_extension(dep_slug)
            if current and range_satisfies(current["version"], dep_range):
                continue  # already satisfied
            dep_entry = extension_registry.get_entry(dep_slug)
            if not dep_entry:
                continue  # unresolvable — assert_required_extensions will raise a clear error
            self._install_required_chain(dep_entry, force=force, _seen=_seen)  # transitive first
            logger.info(f"Installing required dependency '{dep_slug}' before '{entry['slug']}'")
            if dep_entry.get("bundled"):
                self.install_builtin_extension(dep_slug, force=True)
            elif dep_entry.get("source"):
                self.install_extension_from_url(
                    dep_entry["source"], expected_sha256=dep_entry.get("sha256"),
                    force=force, source="registry")

    def check_extension_updates(self, force=False):
        """Compare installed versions against the registry."""
        from devicekit import extension_registry
        from devicekit.extension_manifest import _parse_version
        available = {e["slug"]: e for e in extension_registry.list_extensions(force=force)}
        updates = []
        for ext in self.list_extensions():
            entry = available.get(ext["slug"])
            if not entry:
                continue
            has_update = _parse_version(entry["version"]) > _parse_version(ext["version"])
            updates.append({
                "slug": ext["slug"],
                "installed_version": ext["version"],
                "available_version": entry["version"],
                "has_update": has_update,
            })
        return [u for u in updates if u["has_update"]]

    def update_extension(self, slug, *, force=True):
        """Reinstall an extension at the registry's current version (pinned checksum)."""
        return self.install_extension_from_registry(slug, force=force)

    # ------------------------------------------------------------------
    # Source resolution
    # ------------------------------------------------------------------
    def _resolve_source(self, *, url=None, path=None, zip_bytes=None):
        """Return ``(BytesIO, source_url)`` for any install source."""
        if zip_bytes is not None:
            return io.BytesIO(zip_bytes), ""
        if url is not None:
            return io.BytesIO(self._download_zip(url)), url
        if path is not None:
            return self._zip_local_tree(path), os.path.abspath(path)
        raise ValueError("No install source provided (url, path, or zip_bytes required)")

    def _download_zip(self, url):
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "DeviceKit-Extensions"})
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — curated source
            return resp.read()

    def _zip_local_tree(self, path):
        """Zip a working tree in memory (skipping dev junk) so a local folder flows through
        the exact same install pipeline as a downloaded zip."""
        if not os.path.isdir(path):
            raise ValueError(f"Path is not a directory: {path}")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
                for fn in files:
                    if fn.endswith(_SKIP_FILE_SUFFIXES):
                        continue
                    abs_path = os.path.join(root, fn)
                    rel = os.path.relpath(abs_path, path)
                    zf.write(abs_path, rel.replace(os.sep, "/"))
        buf.seek(0)
        return buf

    def _verify_sha256(self, buf, expected):
        digest = hashlib.sha256(buf.getvalue()).hexdigest()
        if digest.lower() != str(expected).lower():
            raise ValueError(
                f"Checksum mismatch — refusing to install. "
                f"Expected sha256 {expected}, got {digest}.")
        buf.seek(0)

    # ------------------------------------------------------------------
    # Manifest location (handles GitHub zipball nesting)
    # ------------------------------------------------------------------
    def _read_manifest(self, buf):
        buf.seek(0)
        try:
            zf = zipfile.ZipFile(buf)
        except zipfile.BadZipFile:
            raise ValueError("File is not a valid zip archive")
        name, prefix = self._find_manifest(zf)
        manifest = json.loads(zf.read(name))
        return manifest, prefix

    def _find_manifest(self, zf):
        """Locate ``extension.json`` and return ``(name, prefix)`` where ``prefix`` is any
        leading directory (e.g. GitHub's ``repo-sha/``) stripped from other entries."""
        for name in zf.namelist():
            if os.path.basename(name) == "extension.json":
                prefix = name[: -len("extension.json")]
                return name, prefix
        raise ValueError("No extension.json found in archive")

    # ------------------------------------------------------------------
    # Core install pipeline (port of _install_from_buffer)
    # ------------------------------------------------------------------
    def _install_from_buffer(self, buf, *, source, source_url, force=False, hot_load=True):
        buf.seek(0)
        digest = hashlib.sha256(buf.getvalue()).hexdigest()
        manifest, prefix = self._read_manifest(buf)
        validate_manifest(manifest)
        assert_devicekit_compatible(manifest)
        self.assert_required_extensions(manifest)

        slug = manifest["name"]
        existing = self.get_extension(slug)
        if existing and existing["status"] in (STATUS_ACTIVE, STATUS_DISABLED) and not force:
            raise ValueError(
                f"Extension '{slug}' is already installed (v{existing['version']}). "
                f"Uninstall first to reinstall.")

        url_prefix = manifest.get("url_prefix") or f"/extensions/{slug}"
        now = time.time()

        # Persist the row early (status active) so the boot loader / status guard have
        # authoritative state even if hot-load fails.
        with session_scope() as s:
            row = s.get(InstalledExtension, slug)
            if not row:
                row = InstalledExtension(slug=slug, installed_at=now)
                s.add(row)
            row.version = manifest["version"]
            row.display_name = manifest.get("display_name", slug)
            row.category = manifest.get("category", "utility")
            row.manifest = manifest
            row.permissions = manifest.get("permissions", [])
            row.url_prefix = url_prefix
            row.status = STATUS_ACTIVE
            row.source = source
            row.source_url = source_url
            row.sha256 = digest
            row.error = ""
            row.updated_at = now
            if row.config is None:
                row.config = {}

        try:
            self._extract(buf, prefix, slug, manifest)
            if hot_load:
                self._activate_extension(slug, manifest, url_prefix, run_install_hook=True)
        except Exception as e:
            logger.error(f"Extension install failed for '{slug}': {e}")
            with session_scope() as s:
                row = s.get(InstalledExtension, slug)
                if row:
                    row.status = STATUS_ERROR
                    row.error = str(e)
            raise

        logger.info(f"Installed extension '{slug}' v{manifest['version']} ({source})")
        return self.get_extension(slug)

    @staticmethod
    def _pkg_name(slug):
        """Import-safe package name for a slug (dashes aren't valid in Python imports)."""
        return slug.replace("-", "_")

    def _ext_dir(self, slug):
        return os.path.join(_EXTENSIONS_PKG_DIR, self._pkg_name(slug))

    def _extract(self, buf, prefix, slug, manifest):
        """Extract the archive's ``backend/`` subtree to ``devicekit/extensions/<slug>/``
        with Zip-Slip defense. requirements.txt is only pip-installed behind an env flag."""
        dest = self._ext_dir(slug)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(dest, exist_ok=True)

        buf.seek(0)
        zf = zipfile.ZipFile(buf)
        wrote_backend = False
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            rel = member[len(prefix):] if prefix and member.startswith(prefix) else member
            if not rel or rel == "extension.json":
                continue
            if rel.startswith("backend/"):
                inner = rel[len("backend/"):]
                if not inner:
                    continue
                out_path = safe_extract_path(dest, inner)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with zf.open(member) as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                wrote_backend = True
            # frontend/ halves are handled by plan 04; ignored here.

        # Ensure the extracted backend is an importable package and drop the manifest in.
        if not os.path.exists(os.path.join(dest, "__init__.py")):
            open(os.path.join(dest, "__init__.py"), "w").close()
        with open(os.path.join(dest, "extension.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)

        req = os.path.join(dest, "requirements.txt")
        if wrote_backend and os.path.exists(req):
            self._maybe_pip_install(slug, req)

    def _maybe_pip_install(self, slug, req_path):
        if os.environ.get("DEVICEKIT_ALLOW_EXTENSION_PIP", "").lower() in ("1", "true", "yes"):
            logger.warning(f"Installing requirements for extension '{slug}' (pip enabled)")
            subprocess.check_call(["python", "-m", "pip", "install", "-r", req_path])
        else:
            logger.warning(
                f"Extension '{slug}' ships requirements.txt but "
                f"DEVICEKIT_ALLOW_EXTENSION_PIP is not set — skipping (pip runs arbitrary "
                f"code at install time). Review {req_path} and install manually if trusted.")

    # ------------------------------------------------------------------
    # Activation (hot-load) + status guard
    # ------------------------------------------------------------------
    def _activate_extension(self, slug, manifest, url_prefix, run_install_hook=False):
        """Import the extension's backend and wire its contribution points into the running
        app. Blueprint failure is fatal (flips row to error); lifecycle hooks are best-effort."""
        importlib.invalidate_caches()
        entry_point = manifest.get("entry_point")
        if entry_point:
            module_name, _, attr = entry_point.partition(":")
            full = f"devicekit.extensions.{self._pkg_name(slug)}.{module_name}"
            mod = importlib.import_module(full)
            bp = getattr(mod, attr)
            self._register_ext_blueprint(bp, url_prefix, slug)

        # Contribution points (step types / FQL fields / AI tools / models) are wired in
        # Phase 2 via _register_contributions; kept best-effort so a blueprint-only
        # extension activates cleanly.
        try:
            self._register_contributions(slug, manifest)
        except Exception as e:
            logger.warning(f"Contribution registration failed for '{slug}': {e}")

        self._extensions[slug] = {
            "manifest": manifest, "url_prefix": url_prefix, "status": STATUS_ACTIVE,
        }

        if run_install_hook:
            self._run_lifecycle_hook(slug, manifest, "install")

    def _register_contributions(self, slug, manifest):
        """Register an extension's models, step types, FQL fields, and AI tools through the
        SDK. Model creation is a hard failure (tables must exist); everything else is wired
        best-effort so a partial contribution set still yields a usable extension."""
        import devicekit_sdk

        # Fresh AI-tool list + provided-API surface on (re-)activation so we don't double-bind.
        self._ext_ai_tools[slug] = []
        self._ext_extension_api[slug] = {}
        self._ext_contributions.setdefault(slug, {})

        with devicekit_sdk._activating(slug):
            # Models — import the module (registers tables on the shared Base) and create
            # any missing ``ext_<slug>_*`` tables.
            models_ref = manifest.get("models")
            if models_ref:
                func = self._import_ext_ref(slug, models_ref)
                func(devicekit_sdk.db)
                devicekit_sdk.db.create_all()

            # Step types — func returns {type_name: {label, category, config, execute}}.
            steps_ref = manifest.get("step_types")
            if steps_ref:
                specs = self._import_ext_ref(slug, steps_ref)()
                for type_name, spec in (specs or {}).items():
                    devicekit_sdk.register_step_type(type_name, spec)

            # FQL fields — func returns {field_name: {resolver, description}}.
            fql_ref = manifest.get("fql_fields")
            if fql_ref:
                specs = self._import_ext_ref(slug, fql_ref)()
                for field_name, spec in (specs or {}).items():
                    devicekit_sdk.register_fql_field(field_name, spec)

            # AI tools — func receives a binder and registers namespaced tools.
            ai_ref = manifest.get("ai_tools")
            if ai_ref:
                self._import_ext_ref(slug, ai_ref)(devicekit_sdk.ai(slug))

            # Provided API — func receives a binder and registers the curated set of callables
            # siblings may reach through sdk.extension(slug) (plan 17).
            provides_ref = manifest.get("provides")
            if provides_ref:
                self._import_ext_ref(slug, provides_ref)(devicekit_sdk.provides(slug))

            # Jobs — a list of {kind, handler: "module:func"} (matches the manifest spec).
            # Each handler is handler(job_dict) -> result (plan 05).
            for job in (manifest.get("jobs") or []):
                kind = job.get("kind")
                handler_ref = job.get("handler")
                if kind and handler_ref:
                    handler = self._import_ext_ref(slug, handler_ref)
                    devicekit_sdk.jobs.register(kind, handler)

            # Schedules — a list of {name, kind, interval_seconds|cron, payload?,
            # max_attempts?, startup_delay_seconds?}. Owned by the extension so disable/enable
            # pauses/resumes them and uninstall deletes them.
            for spec in (manifest.get("schedules") or []):
                devicekit_sdk.jobs.schedule(
                    spec["name"], spec["kind"],
                    interval_seconds=spec.get("interval_seconds"),
                    cron=spec.get("cron"), payload=spec.get("payload"),
                    max_attempts=spec.get("max_attempts", 1),
                    startup_delay_seconds=spec.get("startup_delay_seconds", 0))

        # Automation templates — ready-made automations shipped by the extension. Registered
        # outside the _activating scope: teardown is by provenance tag (on uninstall), not the
        # per-slug contribution tracker, because these are durable rows the user may edit.
        self._register_automation_templates(slug, manifest)

    _AUTOMATION_SOURCE_TAG = "ext:{slug}"

    def _register_automation_templates(self, slug, manifest):
        """Seed the extension's ``automation_templates`` (a list of JSON paths, relative to the
        extracted backend dir) as real automations, tagged ``ext:<slug>`` for provenance.

        Idempotent: skips any template whose automation (same tag + name) already exists, so it
        is safe to re-run on every boot and on enable. No-op if the host composite lacks the
        AutomationMixin."""
        templates = manifest.get("automation_templates")
        if not templates or not hasattr(self, "create_automation"):
            return
        source_tag = self._AUTOMATION_SOURCE_TAG.format(slug=slug)
        try:
            existing_names = {
                a["name"] for a in self.list_automations()
                if source_tag in (a.get("tags") or [])
            }
        except Exception as e:
            logger.warning(f"Could not list automations for template seeding ('{slug}'): {e}")
            existing_names = set()

        base = self._ext_dir(slug)
        for rel in templates:
            try:
                path = safe_extract_path(base, str(rel))
                if not os.path.isfile(path):
                    logger.warning(f"Extension '{slug}' automation_template not found: {rel}")
                    continue
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                name = data.get("name") or os.path.splitext(os.path.basename(str(rel)))[0]
                if name in existing_names:
                    continue
                tags = list(dict.fromkeys((data.get("tags") or []) + [source_tag]))
                self.create_automation(
                    name=name,
                    description=data.get("description", ""),
                    steps=data.get("steps") or [],
                    tags=tags)
                existing_names.add(name)
                logger.info(f"Seeded automation template '{name}' from extension '{slug}'")
            except Exception as e:
                logger.warning(f"Failed to seed automation_template {rel!r} for '{slug}': {e}")

    def _remove_automation_templates(self, slug):
        """Delete automations this extension seeded (tagged ``ext:<slug>``). Called on uninstall
        so the marketplace round-trips cleanly; disable leaves them in place."""
        if not hasattr(self, "list_automations") or not hasattr(self, "delete_automation"):
            return
        source_tag = self._AUTOMATION_SOURCE_TAG.format(slug=slug)
        try:
            for a in self.list_automations():
                if source_tag in (a.get("tags") or []):
                    self.delete_automation(a["id"])
        except Exception as e:
            logger.warning(f"Failed to remove seeded automations for '{slug}': {e}")

    def _import_ext_ref(self, slug, ref):
        """Resolve a ``module:attr`` manifest reference under ``devicekit.extensions.<slug>``."""
        module_name, _, attr = ref.partition(":")
        mod = importlib.import_module(f"devicekit.extensions.{self._pkg_name(slug)}.{module_name}")
        return getattr(mod, attr)

    def _register_ext_blueprint(self, bp, url_prefix, slug):
        """Register an extension blueprint on the live app with a status guard.

        Flask 3 blocks ``register_blueprint`` after the first request, so we briefly clear
        the ``_got_first_request`` flag (safe: single-process, boot-time registration has
        the flag False already)."""
        app = getattr(self, "_flask_app", None)
        if app is None:
            raise RuntimeError("Flask app not built yet; cannot register extension blueprint")

        self._attach_status_guard(bp, slug)

        # Give each registration a unique blueprint name so reinstall-in-process doesn't
        # collide with a same-named blueprint that Flask can't unregister. URLs are
        # unaffected (they come from the blueprint's routes + url_prefix).
        self._ext_bp_seq += 1
        reg_name = f"ext_{slug.replace('-', '_')}_{self._ext_bp_seq}"

        prev = getattr(app, "_got_first_request", False)
        app._got_first_request = False
        try:
            app.register_blueprint(bp, url_prefix=url_prefix, name=reg_name)
        finally:
            app._got_first_request = prev
        self._extensions.setdefault(slug, {})["bp_name"] = reg_name
        logger.info(f"Registered extension blueprint '{slug}' at {url_prefix}")

    def _attach_status_guard(self, bp, slug):
        """Attach a per-request 503 guard: the in-DB status is authoritative, so a disabled
        or errored extension stops serving without a restart (Flask can't unregister)."""
        if getattr(bp, "_dk_status_guarded", False):
            return
        from flask import jsonify

        def _check():
            row = self.get_extension(slug)
            if not row or row["status"] != STATUS_ACTIVE:
                return jsonify({
                    "error": f"Extension '{slug}' is not active",
                    "status": row["status"] if row else "uninstalled",
                }), 503
            return None

        bp.before_request(_check)
        bp._dk_status_guarded = True

    # ------------------------------------------------------------------
    # Lifecycle hooks (best-effort)
    # ------------------------------------------------------------------
    def _run_lifecycle_hook(self, slug, manifest, phase, **kwargs):
        ref = (manifest.get("lifecycle") or {}).get(phase)
        if not ref:
            return
        try:
            import inspect
            module_name, _, func_name = ref.partition(":")
            full = f"devicekit.extensions.{self._pkg_name(slug)}.{module_name}"
            mod = importlib.import_module(full)
            func = getattr(mod, func_name)
            # Forward only kwargs the hook declares (so on_install(client) and
            # on_uninstall(client, purge=...) both work).
            sig = inspect.signature(func)
            accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
            func(self, **accepted)
            logger.info(f"Ran lifecycle hook '{phase}' for extension '{slug}'")
        except Exception as e:
            logger.warning(f"Lifecycle hook '{phase}' for '{slug}' failed (ignored): {e}")

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------
    def enable_extension(self, slug):
        with session_scope() as s:
            row = s.get(InstalledExtension, slug)
            if not row:
                return None
            row.status = STATUS_ACTIVE
            row.updated_at = time.time()
            result = row.to_dict()
        # Re-register contribution points that disable removed (blueprint stays mounted).
        try:
            self._register_contributions(slug, result["manifest"])
        except Exception as e:
            logger.warning(f"Re-register on enable failed for '{slug}': {e}")
        # Resume the extension's schedules — ensure() preserves the paused flag, so they need
        # an explicit un-pause.
        if hasattr(self, "resume_jobs"):
            try:
                self.resume_jobs("extension", slug)
            except Exception as e:
                logger.warning(f"Resuming schedules for '{slug}' failed: {e}")
        if slug in self._extensions:
            self._extensions[slug]["status"] = STATUS_ACTIVE
        logger.info(f"Enabled extension '{slug}'")
        return result

    def disable_extension(self, slug):
        with session_scope() as s:
            row = s.get(InstalledExtension, slug)
            if not row:
                return None
            row.status = STATUS_DISABLED
            row.updated_at = time.time()
            result = row.to_dict()
        # Deregister in-memory contribution points (step types / FQL fields / AI tools);
        # the blueprint keeps serving 503 via the status guard.
        try:
            self._deregister_contributions(slug, result["manifest"])
        except Exception as e:
            logger.warning(f"Deregister on disable failed for '{slug}': {e}")
        if slug in self._extensions:
            self._extensions[slug]["status"] = STATUS_DISABLED
        # Warn (don't block) if active dependents rely on this extension — their
        # sdk.extension(slug) calls now raise ExtensionUnavailable until it's re-enabled. This
        # is the intended graceful-degradation path (plan 17), not an error.
        dependents = self.active_dependents(slug)
        if dependents:
            logger.warning(
                f"Disabled extension '{slug}' is still required by active extension(s) "
                f"{', '.join(dependents)}; their sdk.extension('{slug}') calls will raise "
                f"ExtensionUnavailable until it is re-enabled.")
        logger.info(f"Disabled extension '{slug}'")
        return result

    def _deregister_contributions(self, slug, manifest):
        """Remove an extension's in-memory contribution points (step types, FQL fields, AI
        tools). These are plain dicts, so removal is trivial — the blueprint keeps serving
        503 via the status guard until a restart."""
        tracked = self._ext_contributions.get(slug, {})
        for type_name in tracked.get("step_types", set()):
            self.unregister_step_type(type_name)
        for field_name in tracked.get("fql_fields", set()):
            self.unregister_fql_field(field_name)
        # Job kinds: drop the handler; pause the extension's schedules as a set so they
        # stop firing (they survive in the DB — resume on re-enable, delete on purge).
        for kind in tracked.get("job_kinds", set()):
            if hasattr(self, "unregister_job_kind"):
                self.unregister_job_kind(kind)
        # Notification catalog entries (plan 06): drop the extension's registered events.
        for event_key in tracked.get("notification_events", set()):
            try:
                from devicekit.notifications import catalog
                catalog.unregister(event_key)
            except Exception:
                pass
        if hasattr(self, "pause_jobs"):
            try:
                self.pause_jobs("extension", slug)
            except Exception as e:
                logger.warning(f"Pausing schedules for '{slug}' failed: {e}")
        self._ext_contributions.pop(slug, None)
        self._ext_ai_tools.pop(slug, None)
        # Drop the sibling-callable surface; sdk.extension(slug) then raises ExtensionUnavailable
        # (the status guard also blocks it, but clearing keeps the map honest).
        self._ext_extension_api.pop(slug, None)

    # ------------------------------------------------------------------
    # Uninstall (keep-data default; purge drops ext_<slug>_* tables)
    # ------------------------------------------------------------------
    def uninstall_extension(self, slug, purge=False, force=False):
        row = self.get_extension(slug)
        if not row:
            return False
        manifest = row["manifest"]

        # Dependency graph (plan 17): block uninstall while an active dependent still requires
        # this extension. Decision (logged here): block rather than warn-and-cascade — cascading
        # uninstalls is surprising and hard to undo; the user disables/uninstalls dependents
        # first, or passes force=True to override.
        dependents = self.active_dependents(slug)
        if dependents and not force:
            raise ValueError(
                f"Cannot uninstall '{slug}': still required by active extension(s) "
                f"{', '.join(dependents)}. Uninstall or disable them first, or force.")

        # Best-effort lifecycle hook + contribution teardown before removing files.
        self._run_lifecycle_hook(slug, manifest, "uninstall", purge=purge)
        try:
            self._deregister_contributions(slug, manifest)
        except Exception as e:
            logger.warning(f"Deregister on uninstall failed for '{slug}': {e}")
        # Remove the extension's schedules entirely (deregister only paused them).
        if hasattr(self, "list_scheduled_jobs") and hasattr(self, "delete_scheduled_job"):
            try:
                for sch in self.list_scheduled_jobs(owner_type="extension", owner_id=slug):
                    self.delete_scheduled_job(sch["id"])
            except Exception as e:
                logger.warning(f"Removing schedules for '{slug}' failed: {e}")

        # Remove automations this extension seeded from its automation_templates.
        self._remove_automation_templates(slug)

        if purge:
            self._drop_ext_tables(slug)

        dest = self._ext_dir(slug)
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)

        with session_scope() as s:
            r = s.get(InstalledExtension, slug)
            if r:
                s.delete(r)
        self._extensions.pop(slug, None)
        logger.info(f"Uninstalled extension '{slug}' (purge={purge})")
        return True

    def _drop_ext_tables(self, slug):
        """Drop exactly the extension's ``ext_<slug>_*`` tables (only on purge)."""
        from sqlalchemy import inspect, text
        prefix = table_prefix(slug)
        engine = get_engine()
        try:
            names = inspect(engine).get_table_names()
        except Exception:
            return 0
        dropped = 0
        with engine.begin() as conn:
            for name in names:
                if name.startswith(prefix):
                    conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
                    dropped += 1
        if dropped:
            logger.info(f"Purged {dropped} table(s) for extension '{slug}'")
        return dropped

    # ------------------------------------------------------------------
    # Boot loader + self-heal
    # ------------------------------------------------------------------
    def load_all_extensions(self, app):
        """At boot: repair any missing extractions, then hot-load every active extension.
        Called from ``build_app`` after the core blueprints register (app not yet serving,
        so blueprint registration is normal)."""
        self.init_extensions()
        self._flask_app = app
        try:
            self.repair_missing_extensions()
        except Exception as e:
            logger.warning(f"Extension repair pass failed: {e}")

        with session_scope() as s:
            rows = [
                (r.slug, r.manifest, r.url_prefix)
                for r in s.query(InstalledExtension)
                .filter(InstalledExtension.status.in_((STATUS_ACTIVE, STATUS_DISABLED)))
                .all()
            ]
        for slug, manifest, url_prefix in rows:
            try:
                self._activate_extension(slug, manifest, url_prefix, run_install_hook=False)
            except Exception as e:
                logger.error(f"Failed to load extension '{slug}': {e}")
                with session_scope() as s:
                    r = s.get(InstalledExtension, slug)
                    if r:
                        r.status = STATUS_ERROR
                        r.error = f"Failed to load: {e}"
        if rows:
            logger.info(f"Loaded {len(rows)} extension(s) at boot")

    def repair_missing_extensions(self):
        """Self-heal extractions lost to an image rebuild: re-install from
        ``builtin-extensions/`` or re-download from ``source_url``."""
        with session_scope() as s:
            candidates = [
                (r.slug, r.source, r.source_url, r.status)
                for r in s.query(InstalledExtension)
                .filter(InstalledExtension.status.in_((STATUS_ACTIVE, STATUS_DISABLED, STATUS_ERROR)))
                .all()
            ]
        for slug, source, source_url, status in candidates:
            entry_init = os.path.join(self._ext_dir(slug), "__init__.py")
            if os.path.exists(entry_init):
                continue  # extraction present
            try:
                if source == "builtin":
                    self._install_from_buffer(
                        self._zip_local_tree(os.path.join(BUILTIN_EXTENSIONS_DIR, source_url or slug)),
                        source="builtin", source_url=source_url, force=True, hot_load=False)
                elif source in ("url", "registry") and source_url:
                    buf = io.BytesIO(self._download_zip(source_url))
                    self._install_from_buffer(
                        buf, source=source, source_url=source_url, force=True, hot_load=False)
                else:
                    with session_scope() as s:
                        r = s.get(InstalledExtension, slug)
                        if r:
                            r.status = STATUS_ERROR
                            r.error = "Extraction missing and no re-install source; re-upload."
                    continue
                logger.info(f"Repaired missing extension '{slug}'")
            except Exception as e:
                logger.error(f"Repair failed for '{slug}': {e}")
                with session_scope() as s:
                    r = s.get(InstalledExtension, slug)
                    if r:
                        r.status = STATUS_ERROR
                        r.error = f"Repair failed: {e}"
