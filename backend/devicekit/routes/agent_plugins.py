"""Agent-plugin manifest endpoints (plan 25 part 5, schema only).

Declare + validate agent-plugin manifests and inspect their dependency order. Install is a
deliberate stub (the on-device runtime is deferred), surfaced honestly rather than hidden.
"""
from flask import Blueprint, jsonify, request

from devicekit.agent_plugin.manifest import AgentPluginError


def make_blueprint(client, limiter):
    bp = Blueprint('agent_plugins', __name__)

    @bp.route('/agent-plugins')
    def plugins_list():
        plugins = client.list_agent_plugins()
        return jsonify({'plugins': plugins, 'count': len(plugins)})

    @bp.route('/agent-plugins/order')
    def plugins_order():
        """Topological install order of declared plugins (or a dependency error)."""
        return jsonify(client.resolve_agent_plugin_order())

    @bp.route('/agent-plugins/validate', methods=['POST'])
    def plugins_validate():
        data = request.get_json(silent=True) or {}
        manifest = data.get('manifest', data)
        return jsonify(client.validate_agent_plugin_manifest(manifest))

    @bp.route('/agent-plugins', methods=['POST'])
    def plugins_declare():
        data = request.get_json(silent=True) or {}
        manifest = data.get('manifest', data)
        try:
            plugin = client.declare_agent_plugin(manifest)
        except AgentPluginError as e:
            return jsonify({'error': 'invalid manifest', 'errors': e.errors}), 400
        return jsonify(plugin), 201

    @bp.route('/agent-plugins/<plugin_id>')
    def plugins_get(plugin_id):
        plugin = client.get_agent_plugin(plugin_id)
        if not plugin:
            return jsonify({'error': 'plugin not found'}), 404
        return jsonify(plugin)

    @bp.route('/agent-plugins/<plugin_id>', methods=['DELETE'])
    def plugins_delete(plugin_id):
        if not client.delete_agent_plugin(plugin_id):
            return jsonify({'error': 'plugin not found'}), 404
        return jsonify({'status': 'deleted'})

    @bp.route('/agent-plugins/<plugin_id>/install', methods=['POST'])
    def plugins_install(plugin_id):
        """Deferred runtime — returns the honest 'not implemented' contract stub."""
        result = client.install_agent_plugin(plugin_id)
        if result.get('error') == 'plugin not declared':
            return jsonify(result), 404
        return jsonify(result), 501  # Not Implemented — schema-only phase

    return bp
