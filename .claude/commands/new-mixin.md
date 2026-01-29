# Create a New Backend Mixin

Create a new backend mixin for DeviceKit. The user will provide: **$ARGUMENTS**

## Steps

1. **Create the mixin file** at `backend/devicekit/mixins/<name>.py` following this exact pattern:

```python
import uuid
import time
import logging

logger = logging.getLogger(__name__)


class <Name>Mixin:
    """<Description>."""

    _<plural_name> = []

    # CRUD and business logic methods here
    # Use uuid.uuid4() for IDs
    # Use time.time() for timestamps
    # Store data in the class-level list
    # Use logger.info() for important operations
```

Reference `backend/devicekit/mixins/alerts.py` and `backend/devicekit/mixins/activity.py` for the exact conventions: class-level list storage, uuid IDs, time.time() timestamps, logger usage.

2. **Register the mixin in `backend/devicekit/client.py`**:
   - Add the import at the top with the other mixin imports
   - Add the class to the `Client` inheritance list (place it before `ApiAppMixin`)

3. **Add API endpoints in `backend/devicekit/mixins/api_app.py`**:
   - Add a new section with a comment separator matching the existing style:
   ```python
   # -----------------------------------------------------------
   # <Feature Name>
   # -----------------------------------------------------------
   ```
   - Add REST endpoints (GET list, POST create, GET by ID, PUT update, DELETE) that call the mixin methods
   - Use `request.get_json(silent=True) or {}` for parsing body
   - Return 404 with `{'error': '...'}` for not found
   - Return 201 for creates
   - Return 204 for deletes
   - Place the new section BEFORE the `# Run` line (`app.run(...)`)

4. **Add frontend API methods in `frontend/src/api.js`**:
   - Add a new comment section
   - Add methods following the existing pattern using the `request()` helper
   - GET with query params: use `URLSearchParams`
   - POST/PUT: use `method` + `body: JSON.stringify(data)`
   - DELETE: use `method: 'DELETE'`

5. **Verify** by reading back client.py and api_app.py to confirm correct integration.
