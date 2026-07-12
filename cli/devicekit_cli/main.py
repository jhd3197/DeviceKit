"""``devicekit`` - thin CLI over the generated DeviceKit API client.

Only the high-value verbs get first-class commands (devices, automations, fleet
queries, metrics, actions, scopes); everything else on the API is reachable through
:class:`devicekit_cli.client.DeviceKitClient` directly.
"""
import json as _json
import sys
from datetime import datetime

import click
import requests

from .client import DeviceKitApiError, DeviceKitClient

DEFAULT_URL = 'http://127.0.0.1:5050'


# ---------------------------------------------------------------- plumbing

def _client(ctx):
    return DeviceKitClient(ctx.obj['url'], ctx.obj['api_key'])


def _fail(message):
    click.echo(f'error: {message}', err=True)
    sys.exit(1)


def _call(fn, *args, **kwargs):
    """Run one API call; API/connection failures exit 1 with the message on stderr."""
    try:
        return fn(*args, **kwargs)
    except DeviceKitApiError as e:
        _fail(f'{e.message} (HTTP {e.status})')
    except requests.exceptions.ConnectionError:
        _fail(f'cannot reach the backend at {fn.__self__.base_url} - is it running? '
              '(set --url or DEVICEKIT_URL)')
    except requests.exceptions.RequestException as e:
        _fail(str(e))


def _echo_json(data):
    click.echo(_json.dumps(data, indent=2, default=str))


def _table(headers, rows):
    """Plain aligned columns - headers, a dash rule, then rows. No deps."""
    rows = [['-' if cell is None or cell == '' else str(cell) for cell in row] for row in rows]
    widths = [max(len(str(h)), *(len(r[i]) for r in rows)) if rows else len(str(h))
              for i, h in enumerate(headers)]

    def line(cells):
        return '  '.join(str(c).ljust(widths[i]) for i, c in enumerate(cells)).rstrip()

    click.echo(line(headers))
    click.echo(line(['-' * w for w in widths]))
    for row in rows:
        click.echo(line(row))


def _flatten(value, prefix=''):
    """Nested dict -> (dotted.key, scalar) pairs; lists are rendered as compact JSON."""
    if isinstance(value, dict):
        for key in value:
            yield from _flatten(value[key], f'{prefix}{key}.' if prefix else f'{key}.')
    else:
        rendered = _json.dumps(value) if isinstance(value, list) else value
        yield prefix.rstrip('.'), '-' if rendered is None else rendered


def _pct(value):
    return '-' if value is None else f'{value}%'


def _ts(epoch):
    try:
        return datetime.fromtimestamp(float(epoch)).strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return str(epoch)


def _device_row(d):
    return [d.get('device_id') or d.get('serial'), d.get('model'),
            d.get('android_version'), 'yes' if d.get('online') else 'no',
            _pct(d.get('battery_level')), d.get('source') or 'adb']


_json_flag = click.option('--json', 'as_json', is_flag=True, help='Print the raw JSON response.')


# ---------------------------------------------------------------- root

@click.group(context_settings={'help_option_names': ['-h', '--help']})
@click.option('--url', envvar='DEVICEKIT_URL', default=DEFAULT_URL, show_default=True,
              metavar='URL', help='Backend base URL (env: DEVICEKIT_URL).')
@click.option('--api-key', envvar='DEVICEKIT_API_KEY', default=None, metavar='KEY',
              help='Scoped dk_ API key (env: DEVICEKIT_API_KEY). Optional in solo/dev mode.')
@click.version_option(package_name='devicekit-cli', prog_name='devicekit')
@click.pass_context
def cli(ctx, url, api_key):
    """DeviceKit fleet CLI - devices, automations, fleet queries, metrics, actions."""
    ctx.ensure_object(dict)
    ctx.obj.update(url=url, api_key=api_key)


# ---------------------------------------------------------------- devices

@cli.group()
def devices():
    """Inspect the device fleet."""


@devices.command('ls')
@_json_flag
@click.pass_context
def devices_ls(ctx, as_json):
    """List devices (ADB-connected and agent-registered)."""
    data = _call(_client(ctx).get_devices)
    if as_json:
        return _echo_json(data)
    rows = [_device_row(d) for d in data.get('devices', []) if d]
    _table(['DEVICE_ID', 'MODEL', 'ANDROID', 'ONLINE', 'BATTERY', 'SOURCE'], rows)
    click.echo(f"\n{data.get('count', len(rows))} device(s)")


@devices.command('info')
@click.argument('device_id')
@_json_flag
@click.pass_context
def devices_info(ctx, device_id, as_json):
    """Show diagnostics for one device."""
    data = _call(_client(ctx).get_devices_by_device_id_diagnostics, device_id)
    if as_json:
        return _echo_json(data)
    pairs = list(_flatten(data))
    width = max((len(k) for k, _ in pairs), default=0)
    for key, value in pairs:
        click.echo(f'{key.ljust(width)}  {value}')


# ---------------------------------------------------------------- automation

@cli.group()
def automation():
    """List and run automations."""


@automation.command('ls')
@_json_flag
@click.pass_context
def automation_ls(ctx, as_json):
    """List saved automations."""
    data = _call(_client(ctx).get_automations)
    if as_json:
        return _echo_json(data)
    rows = [[a.get('id'), a.get('name'), len(a.get('steps') or []),
             (a.get('description') or '')[:60]]
            for a in data.get('automations', [])]
    _table(['ID', 'NAME', 'STEPS', 'DESCRIPTION'], rows)
    click.echo(f"\n{data.get('count', len(rows))} automation(s)")


@automation.command('run')
@click.argument('automation_id')
@click.option('--device', 'device_id', required=True, metavar='DEVICE_ID',
              help='Device to run the automation on.')
@_json_flag
@click.pass_context
def automation_run(ctx, automation_id, device_id, as_json):
    """Run an automation on a device (via POST /actions/invoke)."""
    click.echo('note: the run is gated - this may block while a human approves it.', err=True)
    data = _call(_client(ctx).post_actions_invoke, json={
        'device_id': device_id,
        'action': 'run_automation',
        'args': {'automation_id': automation_id},
    })
    if as_json:
        return _echo_json(data)
    click.echo(data.get('result', ''))
    if data.get('status') == 'denied':
        click.echo('status: denied - approval was declined, timed out, or the device '
                   'is in observe mode.', err=True)


# ---------------------------------------------------------------- fleet

@cli.group()
def fleet():
    """Query the fleet."""


@fleet.command('query')
@click.argument('expression')
@_json_flag
@click.pass_context
def fleet_query(ctx, expression, as_json):
    """Run a fleet query, e.g. devicekit fleet query "online = true and battery_pct < 30"."""
    data = _call(_client(ctx).get_fleet_query, params={'q': expression})
    if as_json:
        return _echo_json(data)
    rows = [_device_row(d) for d in data.get('matches', []) if d]
    _table(['DEVICE_ID', 'MODEL', 'ANDROID', 'ONLINE', 'BATTERY', 'SOURCE'], rows)
    click.echo(f"\n{data.get('count', len(rows))} of {data.get('total', '?')} device(s) matched")


# ---------------------------------------------------------------- metrics

@cli.command('metrics')
@click.argument('device_id')
@click.option('--metric', default='battery_pct', show_default=True,
              help='Metric name (GET /api/v1/metrics/catalog lists them).')
@click.option('--period', default='24h', show_default=True,
              help='Window: 1h, 24h, 7d, or 30d.')
@_json_flag
@click.pass_context
def metrics(ctx, device_id, metric, period, as_json):
    """Show recorded metric history for a device."""
    data = _call(_client(ctx).get_devices_by_device_id_metrics, device_id,
                 params={'metric': metric, 'period': period})
    if as_json:
        return _echo_json(data)
    points = data.get('points', [])
    _table(['TIMESTAMP', 'VALUE'], [[_ts(p.get('ts')), p.get('value')] for p in points])
    click.echo(f"\n{data.get('count', len(points))} point(s) of {data.get('metric', metric)} "
               f"over {data.get('period', period)} (tier: {data.get('tier', '-')})")


# ---------------------------------------------------------------- actions

@cli.command('actions')
@_json_flag
@click.pass_context
def actions(ctx, as_json):
    """List the actions `devicekit command` can invoke, with their required scopes."""
    data = _call(_client(ctx).get_actions)
    if as_json:
        return _echo_json(data)
    rows = [[a.get('name'), 'write' if a.get('is_write') else 'read',
             a.get('category'), a.get('scope'), (a.get('description') or '').split('\n')[0][:60]]
            for a in data.get('actions', [])]
    _table(['ACTION', 'KIND', 'CATEGORY', 'SCOPE', 'DESCRIPTION'], rows)
    click.echo(f"\n{data.get('count', len(rows))} action(s)")


# ---------------------------------------------------------------- command

@cli.command('command')
@click.argument('device_id')
@click.argument('action')
@click.option('--args', 'args_json', default=None, metavar='JSON',
              help='Action arguments as a JSON object, e.g. \'{"x": 540, "y": 1200}\'.')
@_json_flag
@click.pass_context
def command(ctx, device_id, action, args_json, as_json):
    """Invoke one action on a device (`devicekit actions` lists them).

    Write actions wait on the confirmation gate: the call may block until a human
    approves it in the dashboard, and returns DENIED if it is declined or times out.
    """
    try:
        args = _json.loads(args_json) if args_json else {}
    except ValueError as e:
        _fail(f'--args is not valid JSON: {e}')
    if not isinstance(args, dict):
        _fail('--args must be a JSON object')
    click.echo('note: write actions are gated - this may block pending human approval.', err=True)
    data = _call(_client(ctx).post_actions_invoke, json={
        'device_id': device_id, 'action': action, 'args': args,
    })
    if as_json:
        return _echo_json(data)
    click.echo(data.get('result', ''))
    if data.get('status') == 'denied':
        click.echo('status: denied - approval was declined, timed out, or the device '
                   'is in observe mode.', err=True)


# ---------------------------------------------------------------- scopes

@cli.command('scopes')
@_json_flag
@click.pass_context
def scopes(ctx, as_json):
    """Show the assignable API-key scope catalog."""
    data = _call(_client(ctx).get_scopes)
    if as_json:
        return _echo_json(data)
    _table(['SCOPE', 'DESCRIPTION'],
           [[s.get('scope'), s.get('description')] for s in data.get('scopes', [])])
    click.echo(f"\n{data.get('count', 0)} scope(s)")


# ---------------------------------------------------------------- completions

_COMPLETION_SNIPPETS = {
    'bash': ('# Append to ~/.bashrc, then restart your shell:\n'
             'eval "$(_DEVICEKIT_COMPLETE=bash_source devicekit)"'),
    'zsh': ('# Append to ~/.zshrc, then restart your shell:\n'
            'eval "$(_DEVICEKIT_COMPLETE=zsh_source devicekit)"'),
    'fish': ('# Save to ~/.config/fish/completions/devicekit.fish:\n'
             '_DEVICEKIT_COMPLETE=fish_source devicekit | source'),
}

_POWERSHELL_NOTE = '''\
# Click has no native PowerShell completion support, so there is no
# _DEVICEKIT_COMPLETE snippet for PowerShell. Options:
#   - use bash or zsh (WSL / Git Bash) and `devicekit completions bash`;
#   - or register a static completer for the top-level commands by adding
#     the block below to your $PROFILE:
Register-ArgumentCompleter -Native -CommandName devicekit -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    'devices', 'automation', 'fleet', 'metrics', 'actions', 'command', 'scopes', 'completions' |
        Where-Object { $_ -like "$wordToComplete*" } |
        ForEach-Object { [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }
}'''


@cli.command('completions')
@click.argument('shell', type=click.Choice(['bash', 'zsh', 'fish', 'powershell']))
def completions(shell):
    """Print the shell-completion activation snippet for SHELL."""
    click.echo(_COMPLETION_SNIPPETS.get(shell, _POWERSHELL_NOTE))


if __name__ == '__main__':
    cli()
