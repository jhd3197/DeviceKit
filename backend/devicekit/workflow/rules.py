"""Rule-tree evaluation — Python port of ``@tramo/spec`` ``rules.ts``.

rules.ts declares itself the canonical reference for both runtimes ("Both the JS and
Python runtimes implement the same operator semantics; this is the canonical reference.
Keep them in sync."). Operator semantics below mirror it exactly: loose equality with
numeric-string coercion, comparable coercion for ordering, ``contains`` over
string/list/dict, and the empty-group identities (AND of zero = True, OR of zero =
False — a freshly-added If with no rules takes the Yes branch).

The one divergence: ``left``/``right`` expressions run through the AST-allowlist
evaluator (``expr.safe_eval``) instead of ``new Function`` — same lenient
undefined-on-error contract.
"""
import re

from devicekit.workflow.expr import safe_eval


def is_rule_group(value):
    return (
        isinstance(value, dict)
        and value.get("kind") == "group"
        and isinstance(value.get("rules"), list)
    )


def evaluate_rule_group(group, env):
    """``env`` is the tramo ``RuleEvalEnv``: {input, vars, config, steps}."""
    return _evaluate_node(group, env)


def _evaluate_node(node, env):
    if node.get("kind") == "group":
        results = [_evaluate_node(r, env) for r in node.get("rules", [])]
        if node.get("combinator") == "or":
            combined = any(results)
        else:
            combined = all(results)
        return not combined if node.get("not") else combined
    left = safe_eval(node.get("left", ""), env)
    if node.get("rightIsExpr"):
        right = safe_eval(str(node.get("right") or ""), env)
    else:
        right = node.get("right")
    out = _apply_op(node.get("op"), left, right)
    return not out if node.get("not") else out


def _apply_op(op, left, right):
    if op == "=":
        return _loose_equals(left, right)
    if op == "!=":
        return not _loose_equals(left, right)
    if op in (">", ">=", "<", "<="):
        c = _cmp(left, right)
        if c is None:
            return False
        return {">": c > 0, ">=": c >= 0, "<": c < 0, "<=": c <= 0}[op]
    if op == "contains":
        return _contains(left, right)
    if op == "not-contains":
        return not _contains(left, right)
    if op == "starts-with":
        return isinstance(left, str) and isinstance(right, str) and left.startswith(right)
    if op == "ends-with":
        return isinstance(left, str) and isinstance(right, str) and left.endswith(right)
    if op == "matches":
        if not isinstance(left, str) or not isinstance(right, str):
            return False
        try:
            return re.search(right, left) is not None
        except re.error:
            return False
    if op == "in":
        return isinstance(right, list) and any(_loose_equals(v, left) for v in right)
    if op == "not-in":
        return not isinstance(right, list) or not any(_loose_equals(v, left) for v in right)
    if op == "is-empty":
        return _is_empty(left)
    if op == "is-not-empty":
        return not _is_empty(left)
    if op == "exists":
        return left is not None
    if op == "not-exists":
        return left is None
    if op == "is-truthy":
        return bool(left)
    if op == "is-falsy":
        return not left
    return False


def _loose_equals(a, b):
    # bool is an int subclass in Python; keep True != 1 comparisons JS-loose anyway.
    if a is b:
        return True
    if a is None or b is None:
        return False
    if type(a) is type(b) or (isinstance(a, (int, float)) and isinstance(b, (int, float))
                              and not isinstance(a, bool) and not isinstance(b, bool)):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, str):
        return _to_number(b) == a
    if isinstance(b, (int, float)) and isinstance(a, str):
        return _to_number(a) == b
    return a == b


def _to_number(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _to_comparable(v):
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        n = _to_number(v)
        return n if (n is not None and v.strip() != "") else v
    return None


def _cmp(a, b):
    an, bn = _to_comparable(a), _to_comparable(b)
    if an is None or bn is None:
        return None
    if isinstance(an, str) != isinstance(bn, str):
        return None  # mixed string/number never orders (NaN in the TS reference)
    if an < bn:
        return -1
    if an > bn:
        return 1
    return 0


def _contains(haystack, needle):
    if isinstance(haystack, str):
        return str(needle if needle is not None else "") in haystack
    if isinstance(haystack, list):
        return any(_loose_equals(v, needle) for v in haystack)
    if isinstance(haystack, dict):
        return str(needle) in haystack
    return False


def _is_empty(v):
    if v is None:
        return True
    if isinstance(v, str):
        return len(v) == 0
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False
