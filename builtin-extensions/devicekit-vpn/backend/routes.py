"""Blueprint for devicekit-vpn (mounted at ``/ext/devicekit-vpn``).

Device-scoped routes follow the house convention ``/ext/<slug>/devices/<device_id>/<verb>``. The
host attaches a status guard so every route 503s when the extension is disabled. Errors use the
house envelope ``{'error': msg}, status``. Driver refusals (unsupported version, no adapter,
over-ceiling) are distinct AppDriverError subclasses surfaced as 409 so a caller can tell them
apart from a bad request (400) or an install failure (502)."""
from flask import Blueprint, jsonify, request

import devicekit_sdk
from devicekit_sdk import appdriver

from . import driver

SLUG = "devicekit-vpn"
bp = Blueprint("devicekit_vpn", __name__)
log = devicekit_sdk.logger(SLUG)


def _err(message, code):
    return jsonify({"error": message}), code


@bp.route("/ping")
def ping():
    return jsonify({"ok": True, "extension": SLUG, "package": driver.package(),
                    "allowed_countries": driver.allowed_countries()})


@bp.route("/provisioned", methods=["GET"])
def provisioned():
    items = driver.provisioned()
    return jsonify({"provisioned": items, "count": len(items)})


@bp.route("/devices/<device_id>/provision", methods=["POST"])
def provision(device_id):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(driver.provision(device_id, serial=data.get("serial", ""))), 201
    except appdriver.ProvisionError as e:
        return _err(str(e), 502)


@bp.route("/devices/<device_id>/reprovision", methods=["POST"])
def reprovision(device_id):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(driver.reprovision(device_id, serial=data.get("serial", ""))), 201
    except PermissionError as e:
        return _err(str(e), 403)
    except appdriver.ProvisionError as e:
        return _err(str(e), 502)


@bp.route("/devices/<device_id>/connect", methods=["POST"])
def connect(device_id):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(driver.connect(device_id, location=data.get("location")))
    except ValueError as e:                       # country not in the allow-list
        return _err(str(e), 400)
    except appdriver.AppDriverError as e:         # unsupported version / no adapter / over ceiling
        return _err(str(e), 409)


@bp.route("/devices/<device_id>/disconnect", methods=["POST"])
def disconnect(device_id):
    try:
        return jsonify(driver.disconnect(device_id))
    except appdriver.AppDriverError as e:
        return _err(str(e), 409)


@bp.route("/devices/<device_id>/status", methods=["GET"])
def status(device_id):
    try:
        return jsonify(driver.status(device_id))
    except appdriver.AppDriverError as e:
        return _err(str(e), 409)


@bp.route("/devices/<device_id>/egress", methods=["GET"])
def egress(device_id):
    expected = request.args.get("expected_country") or None
    return jsonify(driver.verify_egress(device_id, expected_country=expected))
