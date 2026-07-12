"""AST-allowlist expression evaluator for workflow conditions and sources.

tramo's TS runtime evaluates rule/source expressions with ``new Function`` (sandboxed by
the browser); ServerKit's Python engine used a sandboxed ``eval``. Device automations may
be authored by less-trusted operators, so this port compiles the expression with
:mod:`ast` and walks an explicit node allowlist instead — no ``eval``, no attribute
access on live objects, no callables beyond a tiny builtin set.

Expressions are the JS-ish snippets tramo fields hold (``input.items``, ``vars.count > 3``,
``steps.check.ok && !vars.done``). A light token-level translation maps the JS operators
onto Python (``&&``→``and``, ``||``→``or``, ``!``→``not``, ``===``→``==``, ``true``/
``false``/``null``/``undefined`` → constants) before parsing, so the same expression
string evaluates identically in the editor and here.

Failure contract mirrors tramo's ``evalExpr``: a bad expression returns ``None``
(lenient), it never raises — a typo can't crash a run. Use ``safe_eval(..., strict=True)``
when the caller wants the error surfaced (e.g. a for-each source that must be a list).
"""
import ast
import re

_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Name, ast.Load, ast.Attribute, ast.Subscript, ast.Index, ast.Slice,
    ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.IfExp, ast.Call,
)

#: The only callables an expression may invoke, by bare name.
_ALLOWED_FUNCS = {
    "len": len, "str": str, "int": int, "float": float, "bool": bool,
    "min": min, "max": max, "abs": abs, "round": round, "sum": sum, "sorted": sorted,
}

# JS → Python operator/constant translation. Token-ish regexes, applied outside of
# string literals (expressions here rarely contain strings with these sequences, but
# we split on quotes to be safe).
_JS_REPLACEMENTS = [
    (re.compile(r"==="), "=="),
    (re.compile(r"!=="), "!="),
    (re.compile(r"&&"), " and "),
    (re.compile(r"\|\|"), " or "),
    (re.compile(r"!(?![=])"), " not "),
    (re.compile(r"\btrue\b"), "True"),
    (re.compile(r"\bfalse\b"), "False"),
    (re.compile(r"\bnull\b"), "None"),
    (re.compile(r"\bundefined\b"), "None"),
]

_STRING_SPLIT_RE = re.compile(r"""('[^']*'|"[^"]*")""")


def _translate_js(expr):
    """Apply the JS→Python replacements outside quoted string literals."""
    parts = _STRING_SPLIT_RE.split(expr)
    out = []
    for part in parts:
        if part and part[0] in ("'", '"'):
            out.append(part)
            continue
        for pattern, repl in _JS_REPLACEMENTS:
            part = pattern.sub(repl, part)
        out.append(part)
    return "".join(out)


class UnsafeExpressionError(ValueError):
    pass


def _check_allowed(tree):
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafeExpressionError(
                f"Disallowed syntax in expression: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                raise UnsafeExpressionError("Only builtin helpers (len, str, …) may be called")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise UnsafeExpressionError("Underscore attributes are not allowed")


class _Evaluator(ast.NodeVisitor):
    def __init__(self, env):
        self.env = env

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        return node.value

    def visit_Name(self, node):
        return self.env.get(node.id)

    def visit_Attribute(self, node):
        # Attribute access is dict/list lookup only — never getattr on live objects.
        base = self.visit(node.value)
        return _lookup(base, node.attr)

    def visit_Subscript(self, node):
        base = self.visit(node.value)
        key = self.visit(node.slice) if not isinstance(node.slice, ast.Slice) else None
        if isinstance(node.slice, ast.Slice):
            lo = self.visit(node.slice.lower) if node.slice.lower else None
            hi = self.visit(node.slice.upper) if node.slice.upper else None
            try:
                return base[lo:hi]
            except Exception:
                return None
        return _lookup(base, key)

    def visit_BoolOp(self, node):
        if isinstance(node.op, ast.And):
            result = True
            for v in node.values:
                result = self.visit(v)
                if not result:
                    return result
            return result
        result = False
        for v in node.values:
            result = self.visit(v)
            if result:
                return result
        return result

    def visit_UnaryOp(self, node):
        val = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not val
        if isinstance(node.op, ast.USub):
            return -val
        return +val

    def visit_BinOp(self, node):
        left, right = self.visit(node.left), self.visit(node.right)
        try:
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
        except Exception:
            return None
        return None

    def visit_Compare(self, node):
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            try:
                if isinstance(op, ast.Eq):
                    ok = left == right
                elif isinstance(op, ast.NotEq):
                    ok = left != right
                elif isinstance(op, ast.Lt):
                    ok = left < right
                elif isinstance(op, ast.LtE):
                    ok = left <= right
                elif isinstance(op, ast.Gt):
                    ok = left > right
                elif isinstance(op, ast.GtE):
                    ok = left >= right
                elif isinstance(op, ast.In):
                    ok = left in right
                elif isinstance(op, ast.NotIn):
                    ok = left not in right
                else:
                    return None
            except Exception:
                return None
            if not ok:
                return False
            left = right
        return True

    def visit_List(self, node):
        return [self.visit(e) for e in node.elts]

    def visit_Tuple(self, node):
        return tuple(self.visit(e) for e in node.elts)

    def visit_Dict(self, node):
        return {self.visit(k): self.visit(v) for k, v in zip(node.keys, node.values)}

    def visit_IfExp(self, node):
        return self.visit(node.body) if self.visit(node.test) else self.visit(node.orelse)

    def visit_Call(self, node):
        fn = _ALLOWED_FUNCS[node.func.id]
        args = [self.visit(a) for a in node.args]
        try:
            return fn(*args)
        except Exception:
            return None

    def generic_visit(self, node):
        raise UnsafeExpressionError(f"Unsupported expression node {type(node).__name__}")


def _lookup(base, key):
    """Lenient path lookup — dicts by key, lists by int index, else None."""
    if base is None:
        return None
    if isinstance(base, dict):
        return base.get(key)
    if isinstance(base, (list, tuple)):
        try:
            return base[int(key)]
        except (ValueError, TypeError, IndexError):
            return None
    return None


def safe_eval(expr, env=None, strict=False):
    """Evaluate an allowlisted expression against ``env`` bindings.

    ``env`` holds the tramo binding surface (``input``, ``vars``, ``steps``, ``config``,
    ``trigger``, and per-iteration ``item``/``index``). Returns ``None`` on any parse or
    evaluation problem unless ``strict`` is set, in which case a ``ValueError`` is raised
    with the underlying reason.
    """
    src = (expr or "").strip()
    if not src:
        return None
    try:
        translated = _translate_js(src).strip()
        tree = ast.parse(translated, mode="eval")
        _check_allowed(tree)
        return _Evaluator(env or {}).visit(tree)
    except Exception as e:
        if strict:
            raise ValueError(f"Expression '{src}' failed: {e}") from e
        return None
