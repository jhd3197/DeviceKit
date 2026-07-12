"""devicekit.yaml spec: validation, normalization, aliasing, hashing (plan 23 phase 1)."""
import pytest

from devicekit.policy.spec import (
    PolicySpecError,
    dump_policy_yaml,
    effective_spec_for_device,
    load_policy,
    policy_hash,
)

GOOD_YAML = """
version: 1
name: kiosk-fleet
target:
  group: grp-1
autoApply: false
apps:
  - package: com.expressvpn.vpn
    version: 12.4.0
    extension: devicekit-vpn
automations:
  - automation: nightly-cleanup
    schedule:
      intervalMinutes: 30
settings:
  system:
    screen_brightness: 128
extensions:
  - devicekit-vpn
"""


def test_load_normalizes_and_defaults():
    spec = load_policy(GOOD_YAML)
    assert spec["version"] == 1
    assert spec["target"] == {"group": "grp-1"}
    assert spec["autoApply"] is False
    # Numeric version pin is stringified; enabled defaults true.
    assert spec["apps"][0]["version"] == "12.4.0"
    assert spec["automations"][0]["enabled"] is True
    assert spec["settings"] == {"system": {"screen_brightness": 128}}
    assert spec["extensions"] == ["devicekit-vpn"]
    assert spec["overrides"] == {}


def test_snake_case_aliases_accepted():
    spec = load_policy("""
version: 1
target: {device: SER1}
auto_apply: true
automations:
  - automation: a1
    schedule: {interval_minutes: 15}
settings:
  system:
    api_endpoint: {from_secret: {vault: v1, key: API_URL}}
""")
    assert spec["autoApply"] is True
    assert spec["automations"][0]["schedule"]["intervalMinutes"] == 15
    assert spec["settings"]["system"]["api_endpoint"]["fromSecret"]["key"] == "API_URL"


def test_hash_stable_under_reordering_and_aliases():
    reordered = """
version: 1
extensions: [devicekit-vpn]
settings:
  system: {screen_brightness: 128}
automations:
  - automation: nightly-cleanup
    enabled: true
    schedule: {interval_minutes: 30}
apps:
  - extension: devicekit-vpn
    version: "12.4.0"
    package: com.expressvpn.vpn
auto_apply: false
name: kiosk-fleet
target: {group: grp-1}
"""
    assert policy_hash(load_policy(GOOD_YAML)) == policy_hash(load_policy(reordered))


def test_hash_changes_on_content_change():
    changed = GOOD_YAML.replace("12.4.0", "13.0.1")
    assert policy_hash(load_policy(GOOD_YAML)) != policy_hash(load_policy(changed))


@pytest.mark.parametrize("bad,fragment", [
    ("", "empty"),
    ("just a string", "mapping"),
    ("version: 2\ntarget: {device: x}", "version"),
    ("version: 1", "target"),
    ("version: 1\ntarget: {device: a, group: b}", "target"),
    ("version: 1\ntarget: {}", "target"),
    ("version: 1\ntarget: {device: x}\nbogus: true", "bogus"),
    ("version: 1\ntarget: {device: x}\napps: [{version: '1'}]", "package"),
    ("version: 1\ntarget: {device: x}\nautomations: [{automation: a}]", "schedule"),
    ("version: 1\ntarget: {device: x}\n"
     "settings: {system: {k: {fromSecret: {vault: v}}}}", "not valid"),
    ("version: 1\ntarget: {device: x}\nsettings: {bogus_ns: {k: 1}}", "bogus_ns"),
    ("version: 1\ntarget: {device: x}\n"
     "automations: [{automation: a, schedule: {intervalMinutes: 0}}]", "intervalMinutes"),
])
def test_rejects_invalid(bad, fragment):
    with pytest.raises(PolicySpecError) as exc:
        load_policy(bad)
    assert fragment.lower() in str(exc.value).lower()


def test_error_lists_every_violation():
    with pytest.raises(PolicySpecError) as exc:
        load_policy("version: 3\ntarget: {device: x}\nbogus: 1\napps: [{}]")
    assert len(exc.value.errors) >= 3


def test_effective_spec_merges_override_by_key():
    spec = load_policy(GOOD_YAML + """
overrides:
  moto-1:
    apps:
      - package: com.expressvpn.vpn
        version: 11.0.0
      - package: com.extra.app
    settings:
      system: {screen_brightness: 255}
      global: {stay_on_while_plugged_in: 3}
    extensions: [devicekit-browser]
""")
    eff = effective_spec_for_device(spec, "moto-1")
    by_pkg = {a["package"]: a for a in eff["apps"]}
    assert by_pkg["com.expressvpn.vpn"]["version"] == "11.0.0"   # override wins
    assert "com.extra.app" in by_pkg                              # additive
    assert eff["settings"]["system"]["screen_brightness"] == 255
    assert eff["settings"]["global"]["stay_on_while_plugged_in"] == 3
    assert eff["extensions"] == ["devicekit-browser", "devicekit-vpn"]
    # Devices without an override get the base sections untouched.
    base = effective_spec_for_device(spec, "samsung-1")
    assert base["apps"][0]["version"] == "12.4.0"
    assert base["settings"]["system"]["screen_brightness"] == 128


def test_dump_round_trips():
    spec = load_policy(GOOD_YAML)
    again = load_policy(dump_policy_yaml(spec))
    assert policy_hash(spec) == policy_hash(again)
