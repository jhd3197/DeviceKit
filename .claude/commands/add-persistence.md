# Add DynamoDB Persistence to a Feature

Convert an in-memory data store to DynamoDB persistence. The user will provide: **$ARGUMENTS**

## Context

Read `backend/devicekit/mixins/dynamodb.py` first to understand the available DynamoDB methods:
- `ensure_table_exists(table_name, partition_key, sort_key, ...)`
- `create_dynamodb_record(table_name, records)`
- `get_dynamodb_record(table_name, record_id, key)`
- `get_dynamodb_table(table_name, limit)`
- `update_dynamodb_record(table_name, record_id, update_values, key)`

Also read `backend/config.py` for `DYNAMODB_TABLE_PREFIX` (default: `devicekit_`).

## Steps

1. **Read the target mixin** to understand the current in-memory data structure and all methods that read/write the class-level list.

2. **Add table creation on init**. Add a method to the mixin:
```python
def _ensure_<feature>_table(self):
    self.ensure_table_exists(
        table_name='devicekit_<feature>',
        partition_key='id',
        # Add sort_key if needed for queries
    )
```

3. **Replace writes** -- anywhere the mixin does `self._<items>.append(item)`, also call:
```python
self.create_dynamodb_record('devicekit_<feature>', item)
```

4. **Replace reads** -- anywhere the mixin reads from `self._<items>`, replace with:
```python
# Get all
items = self.get_dynamodb_table('devicekit_<feature>')

# Get by ID
item = self.get_dynamodb_record('devicekit_<feature>', item_id)
```

5. **Replace updates** -- anywhere the mixin modifies items in the list:
```python
self.update_dynamodb_record('devicekit_<feature>', item_id, updated_fields)
```

6. **Keep in-memory as cache** (optional but recommended for performance):
   - Keep the class-level list as a write-through cache
   - Write to both list and DynamoDB on create/update
   - On startup, load from DynamoDB into the list
   - Read from the list for fast access

7. **Add the table name to `backend/config.py`** in the table names section.

8. **Update `docker-compose.yml`** if the DynamoDB local service needs new table init.

9. **Verify** by reading back the modified mixin to ensure all CRUD paths persist.
