"""Backup / DR endpoints (plan 25 part 6).

Create + list + verify backups, run an on-demand restore drill, and read
``restore_confidence`` (the plan-24 doctor check payload). Creating a backup and running a
drill are cheap enough to do inline here; both are also available as scheduled jobs.
"""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('backups', __name__)

    @bp.route('/backups')
    def backups_list():
        backups = client.list_backups()
        return jsonify({'backups': backups, 'count': len(backups)})

    @bp.route('/backups', methods=['POST'])
    def backups_create():
        try:
            backup = client.create_backup()
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(backup), 201

    @bp.route('/backups/<backup_id>')
    def backups_get(backup_id):
        backup = client.get_backup(backup_id)
        if not backup:
            return jsonify({'error': 'backup not found'}), 404
        return jsonify(backup)

    @bp.route('/backups/<backup_id>', methods=['DELETE'])
    def backups_delete(backup_id):
        if not client.delete_backup(backup_id):
            return jsonify({'error': 'backup not found'}), 404
        return jsonify({'status': 'deleted'})

    @bp.route('/backups/<backup_id>/verify', methods=['POST'])
    def backups_verify(backup_id):
        ladder = client.verify_backup(backup_id)
        if ladder is None:
            return jsonify({'error': 'backup not found'}), 404
        return jsonify(ladder)

    @bp.route('/backups/drill', methods=['POST'])
    def backups_drill():
        data = request.get_json(silent=True) or {}
        return jsonify(client.run_restore_drill(backup_id=data.get('backup_id')))

    @bp.route('/backups/restore-confidence')
    def backups_restore_confidence():
        return jsonify(client.restore_confidence())

    return bp
