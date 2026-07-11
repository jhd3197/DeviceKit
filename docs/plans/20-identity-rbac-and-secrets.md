# Plan 20 — Identity, RBAC, Scoped API Keys, Audit & Secrets Vault

**Status:** in progress
**Inspired by:** ServerKit added multi-user tenancy to an *already-shipped single-tenant app
without a rewrite* — the whole retrofit turns on one `scope_query()` helper where **no
workspace context in the request = byte-for-byte the old behavior**
(`backend/app/services/workspace_service.py`, `docs/WORKSPACE_SCOPING.md`). DeviceKit is in the
exact same starting position: a single global `X-API-Key` compared in
`AuthMixin.validate_api_key` (`mixins/auth.py`) + a per-device `X-Agent-Token`, **no users, no
roles, no per-key scopes**, and a `log_activity` trail with no user attribution. This plan ports
ServerKit's identity stack — users, roles, workspaces, hashed *scoped* API keys, a
user-attributed audit service, and a Fernet secrets vault — as the substrate the public API/MCP
(plan 21), webhook triggers (plan 22), and per-extension isolation (plan 19) all quietly assume.
**Depends on:** 01 (persistence — new tables), 02 (blueprints — the auth gate resolves a
principal before blueprint dispatch). Soft: 07/29 (the `X-Agent-Token` machine axis stays
orthogonal), 13 (the AI gate's audit + typed-action model is the same shape as member-action
templates — align, don't fork).

## The questions this plan answers

- **"Can two people share one instance safely?"** Not today — there is exactly one API key and
  everyone who holds it is root. This adds users, a global role (`admin` / `operator` / `viewer`)
  with an editable per-feature read/write matrix, and login/session so the flat key-gate becomes
  *resolve principal → attach to request → gate*.
- **"How do I add multi-user without breaking my solo-localhost setup?"** ServerKit's answer is
  the crown jewel to steal: **opt-in, narrow-only scoping**. A nullable tenant context
  (`X-Workspace-Id`) plus one `scope_query()` helper; with no workspace context the query is
  unfiltered — existing callers keep working untouched. Nothing scopes until someone activates a
  workspace. Adopt this *before* any of the models below.
- **"Who ran that automation / confirmed that AI write / installed that extension?"** DeviceKit
  already produces audit-shaped rows (`AgentAuditLog` for AI tool-calls, `log_activity` for
  everything else) — but identity-less. A central user-attributed `AuditService` (with proxy-aware
  IP/UA and sensitive-key redaction) hangs them off real identities.
- **"Where do fleet credentials live?"** Today: `.env` and the settings table. This adds a
  **Fernet-encrypted secrets vault** (WiFi passwords, app logins, third-party API keys), masked in
  the UI with a separate reveal path, injected into automation runs via a `resolve_env_dict()`
  resolver. DeviceKit already has the Fernet plumbing (`notifications/crypto.py`,
  `DEVICEKIT_SECRET_KEY`) — reuse it.

## The retrofit strategy (do this first, it de-risks everything)

Port ServerKit's `scope_query()` *pattern*, not its code (ServerKit is Flask-SQLAlchemy
`Model.query` + int PKs; DeviceKit is raw declarative `Base` + string-UUID PKs + float-epoch
times — rewrite in DeviceKit's idiom). The contract:

- `resolve_workspace_id(request)` is **deliberately lenient** — a stale/unknown/forbidden
  workspace header degrades to "no scoping" rather than erroring.
- A single `scope_query(query, model, principal)` centralizes the filter. Every list endpoint
  routes through it; with no principal/workspace it returns the query unchanged.
- Two hard rules that run through the whole model: **workspace/grant roles only NARROW, never
  elevate** beyond the global role, and **visibility ≠ permission**.

## Part 1 — Users, global role & the permission matrix

- `User` model (string PK, float timestamps to match the codebase) with a global role and an
  optional JSON per-feature read/write override; resolution = admin ⇒ everything, else custom
  JSON if present, else the role template (`ROLE_PERMISSION_TEMPLATES`). Validate `write` implies
  `read`; reject unknown features.
- DeviceKit's feature axis: `devices`, `automations`, `extensions`, `commands`, `metrics`,
  `notifications`, `settings`, `agents`. A *viewer* sees device state; an *operator* runs
  automations / sends benign commands; an *admin* manages agents/extensions/settings.
- `AuthMixin` grows from `validate_api_key` (string compare) to a principal resolver that attaches
  the user (or the anonymous solo principal when auth is disabled) to the request and gates writes.
  **Solo mode with auth disabled is unchanged.**

## Part 2 — Hashed, scoped, multi API keys (retire the single global key)

- `ApiKey` model stores **only** the sha256 hash + a display prefix (`dk_…` — avoid `sk_`, which
  reads as an OpenAI key), JSON **scopes with wildcard matching** (`devices:*` ⇒ `devices:read`),
  expiry, revoke, and **rotate** (revoke old + recreate same config). Track last-used + IP.
- This is the axis plan 21's public API and MCP server authenticate against. Keep the
  `X-Agent-Token` machine identity **orthogonal** — agent endpoints bypass human RBAC exactly as
  ServerKit keeps host-touching ops outside workspace roles.

## Part 3 — User-attributed audit

- Central `AuditService.log(action, user_id, target_type, target_id, details, ip, ua)` with
  proxy-aware IP/UA extraction, **sensitive-key redaction**, and retention cleanup
  (`services/audit_service.py`, `models/audit_log.py`).
- Fold `log_activity` under it (add `user_id`); keep `AgentAuditLog` focused on AI-gate decisions
  but attribute the approver.

## Part 4 — Workspaces / tenants (the multi-user payoff)

- `Workspace` (name/slug/quotas/status) + `WorkspaceMember` (owner/admin/member/viewer, unique per
  pair, last-owner guard). **A "workspace" scopes *devices + automations*.**
- **Devices are enrolled agents, not user-owned** (like ServerKit's global `Server`): give
  `AgentDevice` a direct `workspace_id` ("born-in-workspace"); let `DeviceGroup` / `DeviceTag` /
  `DeviceCommand` / metrics / automation-runs **derive** scope through `device_id`. `Automation` /
  saved FQL queries carry `workspace_id` directly.
- Capability fold: every path to a resource folds into one **highest-wins tier**
  (viewer < member < admin < owner); a `require_member(min_role)` decorator 404s missing / 403s
  insufficient. Map device danger tiers onto it — read metrics (viewer), run automation / benign
  command (member), factory-reset / uninstall-agent / delete device (admin), and **fleet-wide or
  raw shell/ADB = platform-admin only, never unlockable by a workspace role**.
- `ResourceGrant` (viewer/editor, widens visibility only): share a *single device* or *single
  automation* with a teammate (e.g. a contractor who should see only one kiosk) without whole-fleet
  membership.

## Part 5 — Encrypted secrets vault

- `Vault → Secret`, Fernet-encrypted at rest **reusing `notifications/crypto.py`** (same
  `DEVICEKIT_SECRET_KEY`), masked in list/API with a separate `reveal` path, rotation, expiry,
  `workspace_id`-scoped, and a `resolve_env_dict()` that injects into automation runs (plan 22) at
  execution time.
- **Gotcha:** solo-localhost deployments must not lose the encryption key on reinstall — document
  it loudly (the crypto module already warns when the key is a dev fallback).

## Part 6 (optional) — Auth factors & onboarding

Adopt incrementally once Part 1 lands, each small: **invitations** (token + role/permission preset,
copy-link works without SMTP), **TOTP 2FA + backup codes**, **progressive lockout**
(5 attempts → 5/15/60-min backoff), and a **require-2FA policy with a grace window** anchored on
`max(created_at, policy_enabled_at)` so flipping the toggle never insta-locks veterans (a clean
template for *any* gradual-rollout policy, stored in settings, no new table). SSO/OIDC/SAML and
passkeys are heavier (L) — defer until there are real teams.

## Phases

| Phase | Delivers | Proves | Status |
|---|---|---|---|
| 1 | `User` + login/session + global role + per-feature matrix; `AuthMixin` → principal resolver (solo mode unchanged) | identity substrate exists | ✅ |
| 2 | Hashed scoped multi API keys (`dk_…`, wildcard scopes, rotate/revoke/expiry) replacing the single key | programmatic auth, per-scope | ✅ |
| 3 | `AuditService` (redaction, proxy IP/UA) folding `log_activity` + attributing `AgentAuditLog` | who-did-what | ✅ |
| 4 | `Workspace` + `WorkspaceMember` + opt-in narrow-only `scope_query()` (devices born-in-workspace, children derive) + capability fold + `ResourceGrant` | multi-tenant, no big-bang | ✅ |
| 5 | Fernet secrets vault (reuse `notifications/crypto.py`) — masked list + reveal + `resolve_env_dict` injection | credentials out of `.env` | ✅ |
| 6 | (optional) invitations + TOTP + lockout + require-2FA-with-grace | team onboarding + account security | ✅ |

### Phase 1 — shipped (backend)

Delivered: `services/permissions.py` (role templates + narrow-only override validation, write⇒read),
`services/principal.py` (`Principal` + `feature_for_path`), `services/passwords.py` (bcrypt),
`services/gate.py` (the single `authorize()` decision function the app + tests share), `models/user.py`
(`User` + `UserSession`, string-UUID PKs / float times), `mixins/identity.py` (user CRUD, sessions,
`resolve_principal`, last-admin guards, env-bootstrap admin), `routes/auth.py`
(`/auth/login|logout|session|permissions/schema`, `/users` CRUD admin-only). `api_app` before_request now
resolves principal → attaches to `g` → gates writes. Migration `c0d0a1b2e001`.
**Solo mode unchanged:** auth disabled + no users ⇒ full-access `solo` principal; the first created user flips
the instance to login-required. Verified: 16 new tests + full app boot flow (solo → first user → login → gated
write) + all 300 pre-existing tests green. *Deviation:* Phase-1 UI (login gate + user management) lands in the
consolidated plan-20 frontend commit, not inline.

### Phase 2 — shipped (backend)

Delivered: `models/api_key.py` (`ApiKey`: sha256 hash + `dk_` display prefix, JSON scopes, expiry,
revoke, last-used IP), `services/api_keys.py` (generate/hash, scope catalog + validation),
`mixins/api_keys.py` (create/list/revoke/**rotate** = revoke-old+recreate-same-config,
`resolve_api_key_principal` with throttled last-used tracking), `routes/api_keys.py` (`/api-keys` CRUD +
`/api-keys/scopes`, admin-only, raw key returned once). Wildcard scope matching (`devices:*` ⇒
`devices:read`+`devices:write`, `*` ⇒ all) lives in `Principal.can` and gates the same write path as the
role matrix. The `X-Agent-Token` axis is untouched (orthogonal). Legacy global `API_KEY` still validates
(deprecated, back-compat). Migration `d1e2f3a4b001`. Verified: 11 new tests, clean single migration head.
*Assumption:* key management is admin-only (creator recorded via `created_by`); self-service per-user key
scoping deferred (not required until plan 21).

### Phase 3 — shipped (backend)

Delivered: `services/audit.py` (recursive sensitive-key redaction, proxy-aware `X-Forwarded-For`/`X-Real-IP`
client IP, UA), `models/audit_log.py` (`AuditLog` — attributed, with `username`/`principal_kind` snapshots),
`mixins/audit.py` (`record_audit` one write path, `audit_request` folding the after-request hook,
`get_audit_logs` filters, `purge_audit` retention), `routes/audit.py` (`GET /audit`, admin-only). The
api_app after-request hook now calls `audit_request` → durable attributed row (redacted) **and** the
in-memory `/activities` feed (now carrying `user_id`). `log_activity` grew a `user_id` param; the AI-gate
`confirm` route attributes the approver to the resolved principal's username instead of an API-key prefix.
Migration `e2f3a4b5c001`. Verified: 7 new tests + full suite 334 green.

### Phase 4 — shipped (backend)

Delivered the multi-tenant substrate. `services/workspace.py` is the crown jewel: `scope_query(query,
model, workspace_id)` — **opt-in, narrow-only** (no workspace context ⇒ query unchanged), `resolve_workspace_id`
(lenient `X-Workspace-Id` read), the highest-wins role fold (viewer < member < admin < owner), and
`DEVICE_ACTION_TIERS` / `PLATFORM_ADMIN_ONLY` (fleet-wide + raw shell/ADB never unlockable by a workspace role).
`models/workspace.py` adds `Workspace` + `WorkspaceMember` (unique per pair) + `ResourceGrant` (viewer/editor,
visibility-only). Born-in-workspace `workspace_id` columns added to `agent_devices`, `automations`, `saved_queries`
(nullable ⇒ existing rows global). `mixins/workspaces.py`: workspace/member/grant CRUD, last-owner guards,
`resolve_workspace_context` (lenient — unknown/forbidden degrades to no scoping), `require_member(min_role)`
(404 missing / 403 insufficient, platform-admin bypass), `can_device_action`. `routes/workspaces.py`
(`/workspaces` + `/members` + `/grants`) self-authorize via the fold — **not** the global write gate — so a
global operator who owns a workspace can manage it. The gate attaches the active workspace to the principal;
automation create/list are wired so listing narrows to the active workspace and new automations are born into it.
Migration `f3a4b5c6d001`. Verified: 9 new tests, app-boot scoping flow, full suite 343 green. *Deviation:* the
`/devices` merge (ADB + agent registry) is left unscoped for now — device rows carry `workspace_id` and the
scope helper is available, but rewiring the multi-source merge is deferred to avoid destabilizing fleet listing;
automation scoping is the shipped proof of the pattern.

### Phase 5 — shipped (backend)

Delivered: `models/secret_vault.py` (`Vault` groups `Secret` rows; `workspace_id`-scoped), `mixins/vault.py`
reusing `notifications/crypto.py` (same `DEVICEKIT_SECRET_KEY`) — vault + secret CRUD with values
Fernet-encrypted at rest (`enc:` tokens), a **masked list** (`••••••••` + `has_value`) and a **separate
`reveal_secret`** decryption path, rotation (upsert), expiry, and `resolve_env_dict(vault_id)` — the injection
hook automation runs (plan 22) will call to turn a vault into a `{ENV_VAR: value}` map (expired secrets skipped).
`routes/vault.py` (`/vault/vaults` + `/secrets` + `.../reveal`): admin-gated, reveal is a POST so it's a distinct
audited action, vault listing narrows to the active workspace. Migration `a4b5c6d7e001`. Verified: 7 new tests
(ciphertext-at-rest asserted, reveal round-trip, workspace scoping), full suite 350 green. The crypto module's
dev-fallback-key warning already covers the "don't lose the key on reinstall" gotcha.

### Phase 6 — shipped (backend)

Delivered the opt-in account-security layer. `services/totp.py` (pyotp wrappers: secret, provisioning URI,
verify with ±30s window, single-use backup codes). `models/invitation.py` (`Invitation` — token stored hashed,
role/permission preset, optional workspace membership). `User` gained `totp_secret` (Fernet-encrypted),
`totp_enabled`, `backup_codes` (hashes). `mixins/account_security.py`: **invitations** (create/preview/accept —
copy-link, no SMTP; accept creates the user + optional workspace membership), **TOTP 2FA** (staged enroll →
confirm-with-first-code → backup codes; verify consumes a backup code single-use; disable), **progressive
lockout** (5 failures → 5/15/60-min escalating, in-memory), **`authenticate`** (the composed lockout → password
→ 2FA → session login), and **require-2FA-with-grace** (settings-backed, grace anchored on
`max(created_at, policy_enabled_at)` so enabling never insta-locks a veteran). `routes/auth.py` grew
`/auth/2fa/{setup,confirm,disable}` (self-service), `/invitations` CRUD (admin) + `/invitations/<token>/{preview,accept}`
(public); `/auth/login` now renders the typed `authenticate` result (200 / 429 locked / 401 mfa_required);
`/auth/session` surfaces the 2FA policy status. Migration `b5c6d7e8f001`. Verified: 9 new tests + full-app
invite→accept→enroll→2FA-login flow, full suite 359 green.

Phases 1→2→3 are sequential (2 and 3 need the `User` from 1). Phase 4 is the biggest; it needs 1.
Phase 5 needs 1 (owner attribution) but is otherwise independent. Phase 6 is opt-in polish.

## Decisions to make while executing (log, don't stop)

- **Key prefix:** `dk_` (recommended) vs reusing the bare key format. Pick `dk_` for clean rotation
  + prefix display.
- **Anonymous solo principal vs required login:** default to *auth-disabled = full-access solo
  principal* so the local single-user story never regresses; require login only when a user table
  has ≥1 real user.
- **Workspace on devices:** direct `workspace_id` (born-in-workspace) vs derive-through-owner.
  Devices have no owner — go direct.

## Out of scope

- **SSO/SAML/OIDC and passkeys** as *shipped* — schema-compatible, but the flows are a later add-on
  (ServerKit's `sso_service.py`/`passkey_service.py` are L).
- **Billing / usage-metering quotas.** Workspace quota fields can exist; enforcement/billing is not
  this plan.
- **Per-extension code sandboxing.** Plan 19 contains extension *LLM cost*; real code isolation is
  greenfield in both projects (ServerKit's extensions are also in-process) — not attempted here.

## ServerKit source map (for implementers)

- Retrofit/scoping: `services/workspace_service.py`, `docs/WORKSPACE_SCOPING.md`
- Users/roles: `models/user.py`, `services/permission_service.py`
- Workspaces/membership/grants: `models/workspace.py`, `services/resource_grant_service.py`,
  `services/member_action_service.py`
- API keys: `models/api_key.py`, `services/api_key_service.py`
- Audit: `services/audit_service.py`, `models/audit_log.py`
- Secrets vault: `models/secret_vault.py`, `services/secret_vault_service.py`
- Auth factors: `services/invitation_service.py`, `totp_service.py`, `security_policy_service.py`,
  `login_link_service.py`
- **Idiom mismatch to respect:** ServerKit = Flask-SQLAlchemy `db.Model`, int PKs, `DateTime`,
  `Model.query`. DeviceKit = raw `Base`, string-UUID PKs, float-epoch times, session queries. Port
  the *patterns*, rewrite the *code*.
