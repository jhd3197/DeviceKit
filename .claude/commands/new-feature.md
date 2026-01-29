# Create a Full-Stack Feature

Build a complete vertical feature for DeviceKit. The user will provide: **$ARGUMENTS**

This is the full-stack skill -- it creates everything from backend mixin to frontend view in one shot.

## Steps

### Backend

1. **Create the mixin** at `backend/devicekit/mixins/<name>.py`:
   - Follow the pattern in `backend/devicekit/mixins/alerts.py` and `backend/devicekit/mixins/activity.py`
   - Class-level list storage (`_<plural_name> = []`)
   - UUID IDs via `uuid.uuid4()`, timestamps via `time.time()`
   - Logger via `logging.getLogger(__name__)`
   - CRUD methods + any domain-specific logic

2. **Register in `backend/devicekit/client.py`**:
   - Add import at top
   - Add to `Client` class inheritance (before `ApiAppMixin`)

3. **Add API endpoints in `backend/devicekit/mixins/api_app.py`**:
   - New section with comment separator (`# -----------------------------------------------------------`)
   - REST endpoints: GET list, POST create, GET by ID, PUT update, DELETE
   - Body parsing: `request.get_json(silent=True) or {}`
   - Status codes: 201 for create, 204 for delete, 404 for not found
   - Place BEFORE the `app.run(...)` line

### Frontend

4. **Add API client methods in `frontend/src/api.js`**:
   - New comment section
   - Methods using the `request()` helper
   - GET with params → `URLSearchParams`, POST/PUT → `JSON.stringify`, DELETE → method only

5. **Create the view** at `frontend/src/views/<Name>.jsx`:
   - React functional component with hooks (useState, useEffect, useCallback)
   - Fetch data on mount with loading state
   - Dark theme Tailwind classes: `bg-black`, `bg-zinc-900`, `border-main`, `text-zinc-400`
   - Header with title/subtitle + action buttons
   - Table or card layout for data
   - Reference `frontend/src/views/Automations.jsx` for the full pattern (list + actions + dialog)

6. **Wire routing in `frontend/src/App.jsx`**:
   - Import the view
   - Add `<Route>` to Routes block
   - Add nav item to `navSections` with a lucide-react icon
   - Add the icon to the import block at the top

### Verify

7. Read back `client.py`, `api_app.py`, `api.js`, and `App.jsx` to confirm all integration points are connected.
