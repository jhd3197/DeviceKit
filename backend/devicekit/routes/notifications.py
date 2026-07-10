"""Notifications routes — the bell, the history view, and the event catalog (plan 06).

Read (list + unread count + catalog), act (mark read / mark all / delete / clear), and
inspect per-channel delivery status. List envelopes follow the house convention
(``{'notifications': [...], 'count': N}``); errors are ``{'error': msg}, status``.

Recipient is single-operator (``"default"``) in dev; the ``recipient`` query param is honored
so multi-user can slot in without a route change.
"""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('notifications', __name__)

    def _recipient():
        return request.args.get('recipient', 'default')

    # ── Read ──
    @bp.route('/notifications')
    def notifications_list():
        recipient = _recipient()
        unread_only = request.args.get('unread', '').lower() in ('1', 'true', 'yes')
        severity = request.args.get('severity')
        category = request.args.get('category')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        items = client.list_notifications(
            recipient=recipient, unread_only=unread_only, severity=severity,
            category=category, limit=limit, offset=offset)
        return jsonify({
            'notifications': items,
            'count': len(items),
            'total': client.count_notifications(recipient=recipient),
            'unread': client.unread_notification_count(recipient=recipient),
        })

    @bp.route('/notifications/unread-count')
    def notifications_unread_count():
        return jsonify({'unread': client.unread_notification_count(recipient=_recipient())})

    @bp.route('/notifications/events')
    def notifications_events():
        return jsonify({'events': client.list_notification_events()})

    @bp.route('/notifications/<notification_id>')
    def notifications_get(notification_id):
        notif = client.get_notification(notification_id)
        if not notif:
            return jsonify({'error': 'Notification not found'}), 404
        notif['deliveries'] = client.get_notification_deliveries(notification_id)
        return jsonify(notif)

    # ── Act ──
    @bp.route('/notifications/<notification_id>/read', methods=['PUT'])
    def notifications_mark_read(notification_id):
        data = request.get_json(silent=True) or {}
        read = bool(data.get('read', True))
        notif = client.mark_notification_read(notification_id, read=read)
        if not notif:
            return jsonify({'error': 'Notification not found'}), 404
        return jsonify(notif)

    @bp.route('/notifications/read-all', methods=['PUT'])
    def notifications_mark_all_read():
        n = client.mark_all_notifications_read(recipient=_recipient())
        return jsonify({'status': 'ok', 'updated': n})

    @bp.route('/notifications/<notification_id>', methods=['DELETE'])
    def notifications_delete(notification_id):
        if client.delete_notification(notification_id):
            return jsonify({'status': 'deleted'})
        return jsonify({'error': 'Notification not found'}), 404

    @bp.route('/notifications', methods=['DELETE'])
    def notifications_clear():
        n = client.clear_notifications(recipient=_recipient())
        return jsonify({'status': 'ok', 'deleted': n})

    # ── Delivery channels (webhook / email) ──
    @bp.route('/notifications/channels')
    def notifications_channels_list():
        channels = client.list_notification_channels()
        return jsonify({'channels': channels, 'count': len(channels)})

    @bp.route('/notifications/channels/<channel>')
    def notifications_channel_get(channel):
        return jsonify(client.get_notification_channel(channel))

    @bp.route('/notifications/channels/<channel>', methods=['PUT'])
    def notifications_channel_update(channel):
        data = request.get_json(silent=True) or {}
        try:
            updated = client.set_notification_channel(
                channel, enabled=data.get('enabled'), config=data.get('config'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(updated)

    @bp.route('/notifications/channels/<channel>/test', methods=['POST'])
    def notifications_channel_test(channel):
        result = client.test_notification_channel(channel)
        return jsonify(result), (200 if result.get('ok') else 400)

    return bp
