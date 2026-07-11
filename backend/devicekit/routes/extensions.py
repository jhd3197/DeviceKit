"""Extension platform routes (install pipeline, preview/consent, enable/disable, config).

Registry browse + updates endpoints are added in plan 03 phase 3. Response envelopes follow
the house style: list as ``{'extensions': [...], 'count': N}``, errors as
``{'error': msg}, status``.
"""
import logging

from flask import Blueprint, jsonify, request

from devicekit.extension_manifest import manifest_spec, ManifestError
from devicekit.mixins.extensions import SDK_VERSION

logger = logging.getLogger(__name__)


def make_blueprint(client, limiter):
    bp = Blueprint('extensions', __name__)

    @bp.route('/extensions')
    def extensions_list():
        exts = client.list_extensions()
        return jsonify({'extensions': exts, 'count': len(exts)})

    @bp.route('/extensions/manifest-spec')
    def extensions_manifest_spec():
        return jsonify(manifest_spec())

    @bp.route('/extensions/contributions')
    def extensions_contributions():
        """Merged declarative UI contributions of every active extension (plan 04). The
        React app fetches this once at boot and re-fetches after install/enable/disable to
        render nav items, routes, widgets, palette entries, and page titles dynamically."""
        return jsonify(client.get_contributions_envelope())

    @bp.route('/extensions/sdk-version')
    def extensions_sdk_version():
        return jsonify({'sdk_version': SDK_VERSION})

    @bp.route('/extensions/registry')
    def extensions_registry():
        force = request.args.get('refresh', '').lower() in ('1', 'true', 'yes')
        try:
            return jsonify(client.get_extension_registry(force=force))
        except Exception as e:
            logger.error(f"Registry browse failed: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/extensions/updates')
    def extensions_updates():
        force = request.args.get('refresh', '').lower() in ('1', 'true', 'yes')
        try:
            updates = client.check_extension_updates(force=force)
            return jsonify({'updates': updates, 'count': len(updates)})
        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/extensions/preview', methods=['POST'])
    def extensions_preview():
        data = request.get_json(silent=True) or {}
        url = data.get('url')
        path = data.get('path')
        if not url and not path:
            return jsonify({'error': 'url or path is required'}), 400
        try:
            preview = client.preview_extension(url=url, path=path)
            return jsonify(preview)
        except (ValueError, ManifestError) as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Extension preview failed: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/extensions/install', methods=['POST'])
    def extensions_install():
        data = request.get_json(silent=True) or {}
        slug = data.get('slug')
        url = data.get('url')
        path = data.get('path')
        force = bool(data.get('force', False))
        sha256 = data.get('sha256')
        if not slug and not url and not path:
            return jsonify({'error': 'slug, url, or path is required'}), 400
        try:
            if slug:
                ext = client.install_extension_from_registry(slug, force=force)
            elif url:
                ext = client.install_extension_from_url(
                    url, expected_sha256=sha256, force=force)
            else:
                ext = client.install_extension_from_path(path, force=force)
            return jsonify(ext), 201
        except (ValueError, ManifestError) as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Extension install failed: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/extensions/install-local', methods=['POST'])
    def extensions_install_local():
        """Zip a working tree on disk through the real pipeline (dev loop)."""
        data = request.get_json(silent=True) or {}
        path = data.get('path')
        if not path:
            return jsonify({'error': 'path is required'}), 400
        try:
            ext = client.install_extension_from_path(path, force=bool(data.get('force', True)))
            return jsonify(ext), 201
        except (ValueError, ManifestError) as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Extension install-local failed: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/extensions/install-upload', methods=['POST'])
    def extensions_install_upload():
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'multipart file field "file" is required'}), 400
        force = request.form.get('force', '').lower() in ('1', 'true', 'yes')
        try:
            ext = client.install_extension_from_zip(file.read(), force=force)
            return jsonify(ext), 201
        except (ValueError, ManifestError) as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Extension upload install failed: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/extensions/<slug>')
    def extensions_get(slug):
        ext = client.get_extension(slug)
        if not ext:
            return jsonify({'error': 'Extension not found'}), 404
        return jsonify(ext)

    @bp.route('/extensions/<slug>', methods=['DELETE'])
    def extensions_uninstall(slug):
        purge = request.args.get('purge', '').lower() in ('1', 'true', 'yes')
        force = request.args.get('force', '').lower() in ('1', 'true', 'yes')
        try:
            if client.uninstall_extension(slug, purge=purge, force=force):
                return '', 204
            return jsonify({'error': 'Extension not found'}), 404
        except ValueError as e:
            # Blocked by the dependency graph (an active dependent still requires it).
            return jsonify({'error': str(e)}), 409

    @bp.route('/extensions/<slug>/update', methods=['POST'])
    def extensions_update(slug):
        try:
            ext = client.update_extension(slug)
            return jsonify(ext)
        except (ValueError, ManifestError) as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f"Extension update failed: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/extensions/<slug>/enable', methods=['POST'])
    def extensions_enable(slug):
        result = client.enable_extension(slug)
        if result is None:
            return jsonify({'error': 'Extension not found'}), 404
        return jsonify(result)

    @bp.route('/extensions/<slug>/disable', methods=['POST'])
    def extensions_disable(slug):
        result = client.disable_extension(slug)
        if result is None:
            return jsonify({'error': 'Extension not found'}), 404
        return jsonify(result)

    @bp.route('/extensions/<slug>/config', methods=['GET'])
    def extensions_get_config(slug):
        cfg = client.get_extension_config(slug)
        if cfg is None:
            return jsonify({'error': 'Extension not found'}), 404
        return jsonify({'config': cfg})

    @bp.route('/extensions/<slug>/config', methods=['PUT'])
    def extensions_put_config(slug):
        data = request.get_json(silent=True) or {}
        cfg = client.update_extension_config(slug, data)
        if cfg is None:
            return jsonify({'error': 'Extension not found'}), 404
        return jsonify({'config': cfg})

    return bp
