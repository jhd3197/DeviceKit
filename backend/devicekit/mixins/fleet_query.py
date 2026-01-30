import uuid
import time
import logging
import re
import csv
import io

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query DSL — Tokenizer + Recursive Descent Parser + Evaluator
# ---------------------------------------------------------------------------
#
# Grammar:
#   expression  := or_expr
#   or_expr     := and_expr ('OR' and_expr)*
#   and_expr    := not_expr ('AND' not_expr)*
#   not_expr    := 'NOT' not_expr | comparison
#   comparison  := field operator value
#                | field 'IN' '(' value_list ')'
#                | field 'NOT' 'IN' '(' value_list ')'
#                | field 'LIKE' value
#                | '(' expression ')'
#   operator    := '=' | '!=' | '<' | '>' | '<=' | '>='
#   value       := number | string (quoted or bare)
#   value_list  := value (',' value)*
#

SUPPORTED_FIELDS = {
    'device_id', 'model', 'manufacturer', 'android_version', 'sdk',
    'battery', 'cpu', 'ram_used', 'ram_total', 'temperature',
    'online', 'status', 'agent_status', 'group', 'tags', 'model_name',
}

TOKEN_PATTERNS = [
    ('LPAREN',   r'\('),
    ('RPAREN',   r'\)'),
    ('COMMA',    r','),
    ('OP',       r'!=|<=|>=|<|>|='),
    ('NUMBER',   r'-?\d+(?:\.\d+)?'),
    ('STRING',   r"'[^']*'|\"[^\"]*\""),
    ('KEYWORD',  r'\b(?:AND|OR|NOT|IN|LIKE|TRUE|FALSE)\b'),
    ('IDENT',    r'[a-zA-Z_][a-zA-Z0-9_]*'),
    ('WS',       r'\s+'),
]

_TOKEN_RE = re.compile('|'.join(f'(?P<{name}>{pat})' for name, pat in TOKEN_PATTERNS))


class Token:
    __slots__ = ('type', 'value')

    def __init__(self, type_, value):
        self.type = type_
        self.value = value

    def __repr__(self):
        return f'Token({self.type}, {self.value!r})'


def tokenize(query):
    """Tokenize a query string into a list of Tokens."""
    tokens = []
    for m in _TOKEN_RE.finditer(query):
        kind = m.lastgroup
        val = m.group()
        if kind == 'WS':
            continue
        if kind == 'STRING':
            val = val[1:-1]  # strip quotes
            kind = 'STRING'
        if kind == 'KEYWORD':
            kind = val.upper()  # AND, OR, NOT, IN, LIKE, TRUE, FALSE
        tokens.append(Token(kind, val))
    return tokens


class ParseError(Exception):
    pass


class Parser:
    """Recursive descent parser for the fleet query DSL."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, expected_type=None):
        tok = self.peek()
        if tok is None:
            raise ParseError(f"Unexpected end of expression, expected {expected_type}")
        if expected_type and tok.type != expected_type:
            raise ParseError(f"Expected {expected_type} but got {tok.type} ({tok.value!r})")
        self.pos += 1
        return tok

    def match(self, *types):
        tok = self.peek()
        return tok is not None and tok.type in types

    def parse(self):
        node = self._or_expr()
        if self.pos < len(self.tokens):
            raise ParseError(f"Unexpected token: {self.tokens[self.pos]}")
        return node

    def _or_expr(self):
        left = self._and_expr()
        while self.match('OR'):
            self.consume()
            right = self._and_expr()
            left = ('OR', left, right)
        return left

    def _and_expr(self):
        left = self._not_expr()
        while self.match('AND'):
            self.consume()
            right = self._not_expr()
            left = ('AND', left, right)
        return left

    def _not_expr(self):
        if self.match('NOT'):
            # Check if this is "NOT IN" (peek ahead)
            saved = self.pos
            self.consume()
            if self.match('IN'):
                # This is part of a "field NOT IN (...)" — backtrack
                self.pos = saved
                return self._comparison()
            inner = self._not_expr()
            return ('NOT', inner)
        return self._comparison()

    def _comparison(self):
        # Parenthesized sub-expression
        if self.match('LPAREN'):
            self.consume()
            node = self._or_expr()
            self.consume('RPAREN')
            return node

        # field comparison
        field_tok = self.consume('IDENT')
        field = field_tok.value.lower()

        # NOT IN
        if self.match('NOT'):
            self.consume()
            self.consume('IN')
            self.consume('LPAREN')
            values = self._value_list()
            self.consume('RPAREN')
            return ('NOT_IN', field, values)

        # IN
        if self.match('IN'):
            self.consume()
            self.consume('LPAREN')
            values = self._value_list()
            self.consume('RPAREN')
            return ('IN', field, values)

        # LIKE
        if self.match('LIKE'):
            self.consume()
            val = self._value()
            return ('LIKE', field, val)

        # Regular operator
        op_tok = self.consume('OP')
        val = self._value()
        return ('CMP', field, op_tok.value, val)

    def _value(self):
        tok = self.peek()
        if tok is None:
            raise ParseError("Expected a value")
        if tok.type == 'NUMBER':
            self.consume()
            return float(tok.value) if '.' in tok.value else int(tok.value)
        if tok.type == 'STRING':
            self.consume()
            return tok.value
        if tok.type == 'IDENT':
            self.consume()
            return tok.value
        if tok.type in ('TRUE', 'FALSE'):
            self.consume()
            return tok.type == 'TRUE'
        raise ParseError(f"Unexpected token for value: {tok}")

    def _value_list(self):
        values = [self._value()]
        while self.match('COMMA'):
            self.consume()
            values.append(self._value())
        return values


def parse_query(query_string):
    """Parse a query string into an AST."""
    tokens = tokenize(query_string)
    if not tokens:
        return None
    parser = Parser(tokens)
    return parser.parse()


# ---------------------------------------------------------------------------
# Evaluator — walks AST against a device dict
# ---------------------------------------------------------------------------

def _get_field_value(device, field, fleet_mixin=None):
    """Extract a field value from a device dict, with smart fallbacks."""
    if field == 'device_id':
        return device.get('device_id') or device.get('serial') or ''
    if field == 'model':
        return device.get('model') or device.get('name') or ''
    if field == 'manufacturer':
        return device.get('manufacturer') or ''
    if field == 'android_version':
        v = device.get('android_version') or ''
        try:
            return int(v) if v and v.isdigit() else v
        except (ValueError, TypeError):
            return v
    if field == 'sdk':
        return device.get('sdk') or device.get('sdkInt') or 0
    if field == 'battery':
        return device.get('battery_level') or (device.get('metrics') or {}).get('battery_level') or 0
    if field == 'cpu':
        return device.get('cpu_percent') or (device.get('metrics') or {}).get('cpu_percent') or 0
    if field == 'ram_used':
        return device.get('ram_used_mb') or (device.get('metrics') or {}).get('ram_used_mb') or 0
    if field == 'ram_total':
        return device.get('ram_total_mb') or (device.get('metrics') or {}).get('ram_total_mb') or 0
    if field == 'temperature':
        return (device.get('metrics') or {}).get('temperature') or 0
    if field == 'online':
        return bool(device.get('online', False))
    if field == 'status':
        pkg = device.get('currentPackageName') or ''
        if not device.get('online', True):
            return 'offline'
        if pkg and pkg != 'com.android.launcher3':
            return 'running'
        return 'idle'
    if field == 'agent_status':
        return device.get('source', 'adb')  # 'agent' or 'adb'
    if field == 'group':
        # Check which groups this device belongs to
        if fleet_mixin:
            groups = fleet_mixin.get_groups_for_device(
                device.get('device_id') or device.get('serial') or ''
            )
            return [g['name'] for g in groups]
        return []
    if field == 'tags':
        if fleet_mixin:
            return fleet_mixin.get_device_tags(
                device.get('device_id') or device.get('serial') or ''
            )
        return []
    if field == 'model_name':
        # AI model name from profile, if exists
        return device.get('model_name') or ''
    return device.get(field, '')


def _compare(left, op, right):
    """Compare two values using the given operator."""
    # Type coercion
    if isinstance(right, (int, float)) and isinstance(left, str):
        try:
            left = float(left) if '.' in str(left) else int(left)
        except (ValueError, TypeError):
            pass
    if isinstance(left, (int, float)) and isinstance(right, str):
        try:
            right = float(right) if '.' in str(right) else int(right)
        except (ValueError, TypeError):
            pass

    if op == '=':
        if isinstance(left, str) and isinstance(right, str):
            return left.lower() == right.lower()
        return left == right
    if op == '!=':
        if isinstance(left, str) and isinstance(right, str):
            return left.lower() != right.lower()
        return left != right
    if op == '<':
        return left < right
    if op == '>':
        return left > right
    if op == '<=':
        return left <= right
    if op == '>=':
        return left >= right
    return False


def evaluate_ast(ast, device, fleet_mixin=None):
    """Evaluate an AST node against a device dict. Returns True/False."""
    if ast is None:
        return True

    op = ast[0]

    if op == 'AND':
        return evaluate_ast(ast[1], device, fleet_mixin) and evaluate_ast(ast[2], device, fleet_mixin)
    if op == 'OR':
        return evaluate_ast(ast[1], device, fleet_mixin) or evaluate_ast(ast[2], device, fleet_mixin)
    if op == 'NOT':
        return not evaluate_ast(ast[1], device, fleet_mixin)

    if op == 'CMP':
        _, field, cmp_op, value = ast
        field_val = _get_field_value(device, field, fleet_mixin)
        # Handle boolean comparison
        if isinstance(value, bool):
            return bool(field_val) == value if cmp_op == '=' else bool(field_val) != value
        return _compare(field_val, cmp_op, value)

    if op == 'IN':
        _, field, values = ast
        field_val = _get_field_value(device, field, fleet_mixin)
        if isinstance(field_val, list):
            return any(v in field_val for v in [str(v).lower() for v in values])
        return str(field_val).lower() in [str(v).lower() for v in values]

    if op == 'NOT_IN':
        _, field, values = ast
        field_val = _get_field_value(device, field, fleet_mixin)
        if isinstance(field_val, list):
            return not any(v in field_val for v in [str(v).lower() for v in values])
        return str(field_val).lower() not in [str(v).lower() for v in values]

    if op == 'LIKE':
        _, field, pattern = ast
        field_val = str(_get_field_value(device, field, fleet_mixin)).lower()
        # Convert SQL LIKE pattern to regex: % -> .*, _ -> .
        regex = re.escape(str(pattern).lower()).replace(r'\%', '.*').replace(r'\_', '.')
        return bool(re.fullmatch(regex, field_val))

    return False


# ---------------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    'device_id', 'model', 'manufacturer', 'android_version', 'sdk',
    'battery', 'cpu', 'ram_used', 'ram_total', 'temperature',
    'online', 'status',
]


def devices_to_csv(devices, fleet_mixin=None):
    """Convert a list of device dicts to CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)
    for device in devices:
        row = [_get_field_value(device, col, fleet_mixin) for col in CSV_COLUMNS]
        writer.writerow(row)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------

PRESET_QUERIES = [
    {'name': 'All offline', 'expression': "online = false"},
    {'name': 'Low battery', 'expression': "battery < 20"},
    {'name': 'Critical health', 'expression': "battery < 10 OR temperature > 50 OR cpu > 95"},
    {'name': 'Idle devices', 'expression': "status = 'idle'"},
    {'name': 'Running devices', 'expression': "status = 'running'"},
    {'name': 'Outdated Android', 'expression': "android_version < 12"},
]


class FleetQueryMixin:
    """Fleet Query Language: SQL-like queries across the device fleet."""

    _saved_queries = []

    # -----------------------------------------------------------
    # Query execution
    # -----------------------------------------------------------

    def execute_fleet_query(self, expression, devices=None):
        """Parse and evaluate a query expression against the device fleet.
        Returns list of matching devices."""
        try:
            ast = parse_query(expression)
        except (ParseError, Exception) as e:
            raise ValueError(f"Invalid query: {e}")

        if devices is None:
            # The caller must pass the devices list (api_app does this)
            return []

        return [d for d in devices if evaluate_ast(ast, d, fleet_mixin=self)]

    def validate_query(self, expression):
        """Validate a query without executing it. Returns parse errors if any."""
        try:
            ast = parse_query(expression)
            return {'valid': True, 'ast': str(ast)}
        except (ParseError, Exception) as e:
            return {'valid': False, 'error': str(e)}

    def get_query_fields(self):
        """Return supported query fields with descriptions."""
        return {
            'device_id': 'Device serial / identifier',
            'model': 'Device model name',
            'manufacturer': 'Device manufacturer',
            'android_version': 'Android OS version (numeric)',
            'sdk': 'Android SDK level',
            'battery': 'Battery level (0-100)',
            'cpu': 'CPU usage percent (0-100)',
            'ram_used': 'RAM used in MB',
            'ram_total': 'Total RAM in MB',
            'temperature': 'Device temperature in Celsius',
            'online': 'Whether device is online (true/false)',
            'status': 'Device status (idle, running, offline)',
            'agent_status': 'Connection source (agent, adb)',
            'group': 'Device group membership',
            'tags': 'Device tags',
            'model_name': 'AI model name from profile',
        }

    def get_preset_queries(self):
        """Return built-in preset queries."""
        return list(PRESET_QUERIES)

    # -----------------------------------------------------------
    # Saved queries CRUD
    # -----------------------------------------------------------

    def create_saved_query(self, name, expression, description=''):
        """Save a named query."""
        # Validate first
        validation = self.validate_query(expression)
        if not validation['valid']:
            raise ValueError(f"Invalid query: {validation['error']}")

        query = {
            'id': str(uuid.uuid4()),
            'name': name,
            'expression': expression,
            'description': description,
            'created_at': time.time(),
            'updated_at': time.time(),
        }
        self._saved_queries.append(query)
        logger.info(f"Saved query created: '{name}' ({query['id']})")
        return query

    def get_saved_query(self, query_id):
        return next((q for q in self._saved_queries if q['id'] == query_id), None)

    def list_saved_queries(self):
        return list(self._saved_queries)

    def update_saved_query(self, query_id, updates):
        query = self.get_saved_query(query_id)
        if not query:
            return None
        if 'expression' in updates:
            validation = self.validate_query(updates['expression'])
            if not validation['valid']:
                raise ValueError(f"Invalid query: {validation['error']}")
        for key in ('name', 'expression', 'description'):
            if key in updates:
                query[key] = updates[key]
        query['updated_at'] = time.time()
        return query

    def delete_saved_query(self, query_id):
        before = len(self._saved_queries)
        self._saved_queries = [q for q in self._saved_queries if q['id'] != query_id]
        deleted = len(self._saved_queries) < before
        if deleted:
            logger.info(f"Deleted saved query {query_id}")
        return deleted

    # -----------------------------------------------------------
    # CSV export
    # -----------------------------------------------------------

    def export_query_csv(self, devices):
        """Export a list of devices as CSV."""
        return devices_to_csv(devices, fleet_mixin=self)
