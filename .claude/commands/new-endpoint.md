# Add API Endpoints

Add new REST API endpoints to DeviceKit. The user will provide: **$ARGUMENTS**

## Steps

1. **Read the current state** of `backend/devicekit/mixins/api_app.py` to find the right insertion point.

2. **Add the endpoint section** in `api_app.py` BEFORE the `app.run(...)` line:

```python
        # -----------------------------------------------------------
        # <Feature Name>
        # -----------------------------------------------------------
        @app.route('/<resource>')
        def <resource>_list():
            # GET list
            data = client.<method>()
            return jsonify({'<resource>': data, 'count': len(data)})

        @app.route('/<resource>', methods=['POST'])
        def <resource>_create():
            # POST create
            data = request.get_json(silent=True) or {}
            result = client.<create_method>(**data)
            return jsonify(result), 201

        @app.route('/<resource>/<item_id>')
        def <resource>_get(item_id):
            # GET by ID
            item = client.<get_method>(item_id)
            if item:
                return jsonify(item)
            return jsonify({'error': 'Not found'}), 404

        @app.route('/<resource>/<item_id>', methods=['PUT'])
        def <resource>_update(item_id):
            data = request.get_json(silent=True) or {}
            result = client.<update_method>(item_id, data)
            if result is None:
                return jsonify({'error': 'Not found'}), 404
            return jsonify(result)

        @app.route('/<resource>/<item_id>', methods=['DELETE'])
        def <resource>_delete(item_id):
            if client.<delete_method>(item_id):
                return '', 204
            return jsonify({'error': 'Not found'}), 404
```

Conventions:
- Use `request.get_json(silent=True) or {}` for body parsing
- Use `request.args.get('param')` for query params
- 201 for creates, 204 for deletes, 404 for not found
- Wrap list responses: `{'<resource>': [...], 'count': N}`
- Variable names in routes use `snake_case`

3. **Add frontend API methods** in `frontend/src/api.js`:
   - Add a comment section for the new resource
   - Follow the existing pattern with the `request()` helper

4. **If the endpoints call mixin methods that don't exist yet**, create the mixin first using the pattern from `backend/devicekit/mixins/alerts.py`.

5. **Verify** by reading back api_app.py and api.js.
