# devicekit-cli

A Python client **generated** from the DeviceKit OpenAPI spec, plus a thin
`devicekit` CLI wrapping the high-value verbs (devices, automations, fleet
queries, metrics, actions, scopes).

- `devicekit_cli/client.py` — generated, one method per documented `(path, verb)`
  pair on `/api/v1`. Do not edit; regenerate instead (see below).
- `devicekit_cli/main.py` — the hand-written CLI on top of it.
- `openapi.snapshot.json` — cached spec the client was generated from
  (committed, fully regenerable).

## Install

```bash
pip install -e cli/          # from the repo root
devicekit --help
```

## Auth

Point the CLI at a backend and (outside solo/dev mode) give it a scoped `dk_` key
(create one under **Settings → API Keys** in the dashboard):

```bash
export DEVICEKIT_URL=http://127.0.0.1:5050     # default
export DEVICEKIT_API_KEY=dk_...                # optional in solo/dev mode

# or per invocation:
devicekit --url http://127.0.0.1:5050 --api-key dk_... devices ls
```

`GET /api/v1/scopes` (i.e. `devicekit scopes`) lists the scopes a key can hold;
each generated client method documents its required scope.

## Commands

```bash
devicekit devices ls                          # device table (add --json anywhere for raw JSON)
devicekit devices info R9TT311P25N            # diagnostics for one device

devicekit fleet query "online = true and battery_pct < 30"

devicekit automation ls
devicekit automation run <automation_id> --device R9TT311P25N

devicekit metrics R9TT311P25N --metric battery_pct --period 24h

devicekit actions                             # what `command` can invoke
devicekit command R9TT311P25N tap_screen --args '{"x": 540, "y": 1200}'

devicekit scopes                              # the scope catalog
```

Notes:

- Write actions (`command`, `automation run`) go through the confirmation gate —
  the call **may block until a human approves it** in the dashboard, and returns a
  `DENIED: ...` result (`status: denied`) when declined, timed out, or when the
  device is in observe mode.
- API errors exit with code 1 and print the server's error message on stderr.

## Shell completions

```bash
devicekit completions bash    # eval "$(_DEVICEKIT_COMPLETE=bash_source devicekit)"  -> ~/.bashrc
devicekit completions zsh     # eval "$(_DEVICEKIT_COMPLETE=zsh_source devicekit)"   -> ~/.zshrc
devicekit completions fish    # -> ~/.config/fish/completions/devicekit.fish
devicekit completions powershell   # click has no native PS support; prints guidance
```

## Using the client from Python

```python
from devicekit_cli import DeviceKitClient, DeviceKitApiError

dk = DeviceKitClient('http://127.0.0.1:5050', api_key='dk_...')
for d in dk.get_devices()['devices']:
    print(d['device_id'], d.get('battery_level'))

dk.post_actions_invoke(json={'device_id': 'R9TT311P25N', 'action': 'press_key',
                             'args': {'key': 'home'}})
```

Method names are derived from the path: strip `/api/v1`, `/{param}` becomes
`_by_<param>`, segments join with `_`, prefixed by the HTTP verb — e.g.
`GET /api/v1/devices/{device_id}/diagnostics` → `get_devices_by_device_id_diagnostics`.
Path params are positional; every method also takes `params=` (query) and, for
POST/PUT/PATCH, `json=` (body).

## Regenerating the client

After the API surface changes, refresh the snapshot and the client:

**Offline** (boots the real Flask app, ~15s; device/APK log noise is normal):

```bash
cd backend
python - <<'EOF'
import json
from devicekit import Client
app = Client().build_app()
from devicekit.services.openapi import generate_openapi
with open('../cli/openapi.snapshot.json', 'w', encoding='utf-8') as f:
    json.dump(generate_openapi(app), f, indent=2)
    f.write('\n')
EOF
cd ..
python cli/generate_client.py
```

**From a running backend:**

```bash
python cli/generate_client.py --url http://127.0.0.1:5050/api/v1/openapi.json
```

(`--url` regenerates `client.py` directly from the live spec; to also refresh the
committed snapshot, save `/api/v1/openapi.json` over `cli/openapi.snapshot.json`.)

Commit both `openapi.snapshot.json` and the regenerated `devicekit_cli/client.py`.
