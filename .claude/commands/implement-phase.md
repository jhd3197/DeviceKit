# Implement a Roadmap Phase

Implement a phase from `ROADMAP.md`. The user will provide: **$ARGUMENTS**

## Steps

1. **Read `ROADMAP.md`** and find the specified phase.

2. **Break down the phase** into individual tasks. List them out and confirm the approach before writing code.

3. **For each task in the phase**, determine what type of change it is and follow the appropriate pattern:

   - **New mixin** → Follow the pattern in `backend/devicekit/mixins/alerts.py`:
     - Class-level list storage, uuid IDs, time.time() timestamps, logger
     - Register in `backend/devicekit/client.py` (import + add to Client inheritance before ApiAppMixin)

   - **New API endpoints** → Follow the pattern in `backend/devicekit/mixins/api_app.py`:
     - Comment separator, REST CRUD, proper status codes
     - Insert before `app.run(...)` line

   - **New frontend view** → Follow the pattern in `frontend/src/views/Automations.jsx`:
     - React hooks, dark theme Tailwind, lucide-react icons
     - Add route in `frontend/src/App.jsx`
     - Add nav item to `navSections`

   - **New API client methods** → Follow the pattern in `frontend/src/api.js`:
     - Use the `request()` helper

   - **DynamoDB persistence** → Follow the pattern in `backend/devicekit/mixins/dynamodb.py`:
     - `ensure_table_exists()`, `create_dynamodb_record()`, etc.

4. **Read existing files before editing them.** Never modify a file you haven't read in this session.

5. **After implementing**, read back all modified files to verify integration points are connected:
   - Mixin imported and listed in `client.py`
   - Endpoints registered in `api_app.py`
   - API methods added to `api.js`
   - Route and nav item added to `App.jsx`

6. **Update `ROADMAP.md`** -- mark completed items or add notes about what was implemented.
