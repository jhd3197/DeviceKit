"""CI pipeline / build reporting routes."""
import time
import uuid
import base64
from flask import Blueprint, jsonify, request, Response


def make_blueprint(client, limiter):
    bp = Blueprint('pipeline', __name__)

    @bp.route('/pipeline/builds')
    def pipeline_builds():
        return jsonify({
            'builds': sorted(client._builds, key=lambda b: b['created_at'], reverse=True)
        })

    @bp.route('/pipeline/builds/<build_id>')
    def pipeline_build_detail(build_id):
        build = next((b for b in client._builds if b['id'] == build_id), None)
        if build:
            return jsonify(build)
        return jsonify({'error': 'Build not found'}), 404

    @bp.route('/pipeline/builds', methods=['POST'])
    def pipeline_start_build():
        data = request.get_json(silent=True) or {}
        build_num = len(client._builds) + 1
        build = {
            'id': str(uuid.uuid4()),
            'number': build_num,
            'title': data.get('title', f'Build #{build_num}'),
            'status': 'created',
            'source': data.get('source', 'manual'),
            'ci_url': data.get('ci_url', ''),
            'created_at': time.time(),
            'started_at': None,
            'finished_at': None,
            'duration_ms': None,
            'total_tests': data.get('total_tests', 0),
            'passed': 0,
            'failed': 0,
            'errors': 0,
            'skipped': 0,
            'success_rate': 0,
            'tests': [],
            'failures': [],
        }
        client._builds.append(build)
        client.log_activity('build_started', details={'build_id': build['id']})
        client.broadcast('pipeline_build', build)
        return jsonify(build), 201

    @bp.route('/pipeline/builds/<build_id>/status', methods=['PUT'])
    def pipeline_build_status(build_id):
        build = next((b for b in client._builds if b['id'] == build_id), None)
        if not build:
            return jsonify({'error': 'Build not found'}), 404
        data = request.get_json(silent=True) or {}
        new_status = data.get('status', '')
        if new_status not in ('running', 'completed', 'failed'):
            return jsonify({'error': 'Invalid status. Must be running, completed, or failed'}), 400

        build['status'] = new_status
        if new_status == 'running' and not build['started_at']:
            build['started_at'] = time.time()
        elif new_status in ('completed', 'failed'):
            build['finished_at'] = time.time()
            if build['started_at']:
                build['duration_ms'] = int((build['finished_at'] - build['started_at']) * 1000)

            total = len(build['tests'])
            if total > 0:
                build['success_rate'] = round(build['passed'] / total * 100, 1)

        client.broadcast('pipeline_build', build)
        return jsonify(build)

    @bp.route('/pipeline/builds/<build_id>/tests', methods=['POST'])
    def pipeline_build_report_test(build_id):
        build = next((b for b in client._builds if b['id'] == build_id), None)
        if not build:
            return jsonify({'error': 'Build not found'}), 404
        data = request.get_json(silent=True) or {}

        test_record = {
            'id': data.get('id', str(uuid.uuid4())),
            'name': data.get('name', ''),
            'status': data.get('status', 'pass'),
            'duration': data.get('duration', 0),
            'device': data.get('device', ''),
            'error_message': data.get('error_message', ''),
            'traceback': data.get('traceback', ''),
            'screenshot_b64': data.get('screenshot_b64'),
            'reported_at': time.time(),
        }
        build['tests'].append(test_record)

        # Update counters
        status = test_record['status']
        if status == 'pass':
            build['passed'] += 1
        elif status == 'fail':
            build['failed'] += 1
            build['failures'].append({
                'test_id': test_record['id'],
                'test_name': test_record['name'],
                'error': test_record['error_message'],
                'trace': test_record['traceback'],
            })
        elif status == 'error':
            build['errors'] += 1
            build['failures'].append({
                'test_id': test_record['id'],
                'test_name': test_record['name'],
                'error': test_record['error_message'],
                'trace': test_record['traceback'],
            })
        elif status == 'skip':
            build['skipped'] += 1

        total = len(build['tests'])
        if total > 0:
            build['success_rate'] = round(build['passed'] / total * 100, 1)

        client.broadcast('pipeline_test', {
            'build_id': build_id,
            'test': test_record,
            'passed': build['passed'],
            'failed': build['failed'],
            'errors': build['errors'],
            'skipped': build['skipped'],
            'total': total,
            'success_rate': build['success_rate'],
        })
        return jsonify(test_record), 201

    @bp.route('/pipeline/builds/<build_id>/tests/bulk', methods=['POST'])
    def pipeline_build_report_tests_bulk(build_id):
        build = next((b for b in client._builds if b['id'] == build_id), None)
        if not build:
            return jsonify({'error': 'Build not found'}), 404
        data = request.get_json(silent=True) or {}
        tests_data = data.get('tests', [])
        added = []

        for t in tests_data:
            test_record = {
                'id': t.get('id', str(uuid.uuid4())),
                'name': t.get('name', ''),
                'status': t.get('status', 'pass'),
                'duration': t.get('duration', 0),
                'device': t.get('device', ''),
                'error_message': t.get('error_message', ''),
                'traceback': t.get('traceback', ''),
                'screenshot_b64': t.get('screenshot_b64'),
                'reported_at': time.time(),
            }
            build['tests'].append(test_record)
            added.append(test_record)

            status = test_record['status']
            if status == 'pass':
                build['passed'] += 1
            elif status == 'fail':
                build['failed'] += 1
                build['failures'].append({
                    'test_id': test_record['id'],
                    'test_name': test_record['name'],
                    'error': test_record['error_message'],
                    'trace': test_record['traceback'],
                })
            elif status == 'error':
                build['errors'] += 1
                build['failures'].append({
                    'test_id': test_record['id'],
                    'test_name': test_record['name'],
                    'error': test_record['error_message'],
                    'trace': test_record['traceback'],
                })
            elif status == 'skip':
                build['skipped'] += 1

        total = len(build['tests'])
        if total > 0:
            build['success_rate'] = round(build['passed'] / total * 100, 1)

        client.broadcast('pipeline_test', {
            'build_id': build_id,
            'bulk': True,
            'count': len(added),
            'passed': build['passed'],
            'failed': build['failed'],
            'errors': build['errors'],
            'skipped': build['skipped'],
            'total': total,
            'success_rate': build['success_rate'],
        })
        return jsonify({'tests': added, 'count': len(added)}), 201

    @bp.route('/pipeline/builds/<build_id>/screenshots/<int:test_index>')
    def pipeline_build_screenshot(build_id, test_index):
        build = next((b for b in client._builds if b['id'] == build_id), None)
        if not build:
            return jsonify({'error': 'Build not found'}), 404
        tests_list = build.get('tests', [])
        if test_index < 0 or test_index >= len(tests_list):
            return jsonify({'error': 'Test index out of range'}), 404
        screenshot_b64 = tests_list[test_index].get('screenshot_b64')
        if not screenshot_b64:
            return jsonify({'error': 'No screenshot for this test'}), 404
        data = base64.b64decode(screenshot_b64)
        return Response(data, mimetype='image/png')

    @bp.route('/pipeline/builds/<build_id>/failures')
    def pipeline_build_failures(build_id):
        build = next((b for b in client._builds if b['id'] == build_id), None)
        if not build:
            return jsonify({'error': 'Build not found'}), 404
        return jsonify({'failures': build.get('failures', [])})

    return bp
