"""Server-Sent Events (SSE) stream route.

The broadcast infrastructure and client registry live on ``EventsMixin``
(``client.broadcast`` / ``client.sse_stream``); this blueprint only exposes the HTTP
endpoint.
"""
from flask import Blueprint, Response


def make_blueprint(client, limiter):
    bp = Blueprint('events', __name__)

    @bp.route('/events/stream')
    def sse_stream():
        return Response(
            client.sse_stream(),
            mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    return bp
