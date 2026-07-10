"""Jobs routes — inspect and control the unified job system (plan 05).

Read/observe background work (recent + failed jobs, per-status/kind stats) and act on it
(retry a failed job, cancel a pending one). Also exposes the DB-defined schedules so an
operator can see cadence and run one on demand. List envelopes follow the house convention
(``{'jobs': [...], 'count': N}``); errors are ``{'error': msg}, status``.
"""
from flask import Blueprint, jsonify, request


def make_blueprint(client, limiter):
    bp = Blueprint('jobs', __name__)

    # ── Jobs ──
    @bp.route('/jobs')
    def jobs_list():
        status = request.args.get('status')
        kind = request.args.get('kind')
        owner_type = request.args.get('owner_type')
        owner_id = request.args.get('owner_id')
        q = request.args.get('q')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        jobs = client.list_jobs(
            status=status, kind=kind, owner_type=owner_type, owner_id=owner_id,
            q=q, limit=limit, offset=offset,
        )
        total = client.count_jobs(
            status=status, kind=kind, owner_type=owner_type, owner_id=owner_id, q=q,
        )
        return jsonify({'jobs': jobs, 'count': len(jobs), 'total': total})

    @bp.route('/jobs/stats')
    def jobs_stats():
        return jsonify(client.job_stats())

    @bp.route('/jobs/<job_id>')
    def jobs_get(job_id):
        job = client.get_job(job_id)
        if job:
            return jsonify(job)
        return jsonify({'error': 'Job not found'}), 404

    @bp.route('/jobs/<job_id>/retry', methods=['POST'])
    def jobs_retry(job_id):
        job = client.retry_job(job_id)
        if job is None:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify(job)

    @bp.route('/jobs/<job_id>/cancel', methods=['POST'])
    def jobs_cancel(job_id):
        job = client.cancel_job(job_id)
        if job is None:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify(job)

    # ── Scheduled jobs ──
    @bp.route('/jobs/schedules')
    def scheduled_jobs_list():
        owner_type = request.args.get('owner_type')
        owner_id = request.args.get('owner_id')
        schedules = client.list_scheduled_jobs(owner_type=owner_type, owner_id=owner_id)
        return jsonify({'schedules': schedules, 'count': len(schedules)})

    @bp.route('/jobs/schedules/<int:scheduled_job_id>/run', methods=['POST'])
    def scheduled_jobs_run(scheduled_job_id):
        job = client.run_scheduled_job_now(scheduled_job_id)
        if job is None:
            return jsonify({'error': 'Schedule not found'}), 404
        return jsonify(job), 201

    @bp.route('/jobs/schedules/<int:scheduled_job_id>', methods=['PUT'])
    def scheduled_jobs_update(scheduled_job_id):
        data = request.get_json(silent=True) or {}
        if 'enabled' not in data:
            return jsonify({'error': 'enabled is required'}), 400
        sched = client.set_scheduled_job_enabled(scheduled_job_id, bool(data['enabled']))
        if sched is None:
            return jsonify({'error': 'Schedule not found'}), 404
        return jsonify(sched)

    return bp
