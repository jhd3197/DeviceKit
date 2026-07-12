"""Automation routes (CRUD, runs, recording, schedules, AI generation)."""
import base64

from flask import Blueprint, jsonify, request, Response, g

from devicekit.services.scopes import require_scope


def _workspace_id():
    """The active workspace the gate attached to the principal (plan 20 part 4), or None."""
    return getattr(getattr(g, 'principal', None), 'workspace_id', None)


def make_blueprint(client, limiter):
    bp = Blueprint('automations', __name__)

    @bp.route('/automations/step-types')
    @require_scope('automations:read')
    def automation_step_types():
        return jsonify(client.get_step_types())

    @bp.route('/automations')
    @require_scope('automations:read')
    def automations_list():
        # Narrowed to the active workspace when one is set; otherwise unchanged (all automations).
        automations = client.list_automations(workspace_id=_workspace_id())
        return jsonify({'automations': automations, 'count': len(automations)})

    @bp.route('/automations', methods=['POST'])
    @require_scope('automations:write')
    def automations_create():
        data = request.get_json(silent=True) or {}
        name = data.get('name', '')
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        automation = client.create_automation(
            name=name,
            description=data.get('description', ''),
            steps=data.get('steps', []),
            tags=data.get('tags', []),
            workspace_id=_workspace_id(),   # born into the active workspace, if any
        )
        return jsonify(automation), 201

    @bp.route('/automations/<automation_id>')
    @require_scope('automations:read')
    def automations_get(automation_id):
        automation = client.get_automation(automation_id)
        if automation:
            return jsonify(automation)
        return jsonify({'error': 'Automation not found'}), 404

    @bp.route('/automations/<automation_id>', methods=['PUT'])
    @require_scope('automations:write')
    def automations_update(automation_id):
        data = request.get_json(silent=True) or {}
        result = client.update_automation(automation_id, data)
        if result is None:
            return jsonify({'error': 'Automation not found'}), 404
        updated = client.get_automation(automation_id)
        return jsonify(updated)

    @bp.route('/automations/<automation_id>', methods=['DELETE'])
    @require_scope('automations:write')
    def automations_delete(automation_id):
        if client.delete_automation(automation_id):
            return '', 204
        return jsonify({'error': 'Automation not found'}), 404

    @bp.route('/automations/<automation_id>/run', methods=['POST'])
    @require_scope('automations:run')
    def automations_run(automation_id):
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        if not device_id:
            return jsonify({'error': 'device_id is required'}), 400
        self_heal = bool(data.get('self_heal', False))
        try:
            run_record = client.execute_automation(automation_id, device_id, self_heal=self_heal)
            return jsonify(run_record), 201
        except ValueError as e:
            return jsonify({'error': str(e)}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/automations/runs')
    @require_scope('automations:read')
    def automation_runs_list():
        automation_id = request.args.get('automation_id')
        device_id = request.args.get('device_id')
        limit = int(request.args.get('limit', 50))
        runs = client.list_automation_runs(
            automation_id=automation_id,
            device_id=device_id,
            limit=limit,
        )
        return jsonify({'runs': runs, 'count': len(runs)})

    @bp.route('/automations/runs/<run_id>')
    @require_scope('automations:read')
    def automation_runs_get(run_id):
        run = client.get_automation_run(run_id)
        if run:
            return jsonify(run)
        return jsonify({'error': 'Run not found'}), 404

    @bp.route('/automations/runs/<run_id>/cancel', methods=['POST'])
    @require_scope('automations:run')
    def automation_runs_cancel(run_id):
        if client.cancel_automation_run(run_id):
            return jsonify({'status': 'cancelling'})
        return jsonify({'error': 'Run not found or already finished'}), 404

    # ── Recording ──
    @bp.route('/automations/record/start', methods=['POST'])
    @require_scope('automations:write')
    def automation_record_start():
        data = request.get_json(silent=True) or {}
        device_id = data.get('device_id')
        if not device_id:
            return jsonify({'error': 'device_id is required'}), 400
        try:
            session = client.start_recording(device_id)
            return jsonify(session), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/automations/record/stop', methods=['POST'])
    @require_scope('automations:write')
    def automation_record_stop():
        data = request.get_json(silent=True) or {}
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400
        try:
            steps = client.stop_recording(session_id)
            return jsonify({'steps': steps})
        except ValueError as e:
            return jsonify({'error': str(e)}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/automations/record/action', methods=['POST'])
    @require_scope('automations:write')
    def automation_record_action():
        data = request.get_json(silent=True) or {}
        session_id = data.get('session_id')
        action = data.get('action')
        if not session_id or not action:
            return jsonify({'error': 'session_id and action are required'}), 400
        try:
            count = client.record_action(session_id, action)
            return jsonify({'count': count})
        except ValueError as e:
            return jsonify({'error': str(e)}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ── Schedules ──
    @bp.route('/automations/schedules')
    @require_scope('automations:read')
    def automation_schedules_list():
        automation_id = request.args.get('automation_id')
        schedules = client.list_schedules(automation_id=automation_id)
        return jsonify({'schedules': schedules, 'count': len(schedules)})

    @bp.route('/automations/schedules', methods=['POST'])
    @require_scope('automations:write')
    def automation_schedules_create():
        data = request.get_json(silent=True) or {}
        automation_id = data.get('automation_id')
        device_id = data.get('device_id')
        interval_minutes = data.get('interval_minutes')
        if not automation_id or not device_id or not interval_minutes:
            return jsonify({'error': 'automation_id, device_id and interval_minutes are required'}), 400
        try:
            schedule = client.create_schedule(
                automation_id=automation_id,
                device_id=device_id,
                interval_minutes=int(interval_minutes),
                enabled=data.get('enabled', True),
            )
            return jsonify(schedule), 201
        except ValueError as e:
            return jsonify({'error': str(e)}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/automations/schedules/<schedule_id>', methods=['PUT'])
    @require_scope('automations:write')
    def automation_schedules_update(schedule_id):
        data = request.get_json(silent=True) or {}
        result = client.update_schedule(schedule_id, data)
        if result is None:
            return jsonify({'error': 'Schedule not found'}), 404
        return jsonify(result)

    @bp.route('/automations/schedules/<schedule_id>', methods=['DELETE'])
    @require_scope('automations:write')
    def automation_schedules_delete(schedule_id):
        if client.delete_schedule(schedule_id):
            return '', 204
        return jsonify({'error': 'Schedule not found'}), 404

    # ── Failure Screenshots ──
    @bp.route('/automations/runs/<run_id>/screenshots/<int:step_index>')
    @require_scope('automations:read')
    def automation_run_screenshot(run_id, step_index):
        run = client.get_automation_run(run_id)
        if not run:
            return jsonify({'error': 'Run not found'}), 404
        step_results = run.get('step_results', [])
        if step_index < 0 or step_index >= len(step_results):
            return jsonify({'error': 'Step index out of range'}), 404
        screenshot_b64 = step_results[step_index].get('failure_screenshot')
        if not screenshot_b64:
            return jsonify({'error': 'No failure screenshot for this step'}), 404
        import base64
        data = base64.b64decode(screenshot_b64)
        return Response(data, mimetype='image/png')

    # ── Clone / Export / Import ──
    @bp.route('/automations/<automation_id>/clone', methods=['POST'])
    @require_scope('automations:write')
    def automations_clone(automation_id):
        data = request.get_json(silent=True) or {}
        try:
            cloned = client.clone_automation(automation_id, new_name=data.get('name'))
            return jsonify(cloned), 201
        except ValueError as e:
            return jsonify({'error': str(e)}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/automations/<automation_id>/export')
    @require_scope('automations:read')
    def automations_export(automation_id):
        try:
            exported = client.export_automation(automation_id)
            return jsonify(exported)
        except ValueError as e:
            return jsonify({'error': str(e)}), 404
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/automations/import', methods=['POST'])
    @require_scope('automations:write')
    def automations_import():
        data = request.get_json(silent=True) or {}
        if not data.get('name'):
            return jsonify({'error': 'name is required'}), 400
        try:
            automation = client.import_automation(data)
            return jsonify(automation), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ── NL Automation (AI-powered) ──
    @bp.route('/automations/generate', methods=['POST'])
    @require_scope('automations:write')
    def automations_generate():
        data = request.get_json(silent=True) or {}
        description = data.get('description', '')
        if not description:
            return jsonify({'error': 'description is required'}), 400
        device_id = data.get('device_id')
        try:
            result = client.generate_automation_steps(description, device_id=device_id)
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/automations/refine-step', methods=['POST'])
    @require_scope('automations:write')
    def automations_refine_step():
        data = request.get_json(silent=True) or {}
        step = data.get('step')
        instruction = data.get('instruction', '')
        if not step or not instruction:
            return jsonify({'error': 'step and instruction are required'}), 400
        device_id = data.get('device_id')
        try:
            refined = client.refine_step(step, instruction, device_id=device_id)
            return jsonify(refined)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/automations/<automation_id>/explain')
    @require_scope('automations:read')
    def automations_explain(automation_id):
        try:
            result = client.explain_automation(automation_id)
            if 'error' in result and result['error'] == 'Automation not found':
                return jsonify(result), 404
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/devices/<device_id>/ui-hierarchy')
    @require_scope('devices:read')
    def device_ui_hierarchy(device_id):
        try:
            hierarchy = client.fetch_ui_hierarchy(device_id)
            if hierarchy:
                return jsonify(hierarchy)
            return jsonify({'error': 'Could not fetch UI hierarchy'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return bp
