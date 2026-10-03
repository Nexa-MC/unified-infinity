"""Explicit conservative subsets, not replacements for Fabric/Maven resolvers."""
import re
from functools import total_ordering


class UnsupportedVersion(ValueError):
    pass


@total_ordering
class Version:
    def __init__(self, value):
        if not isinstance(value, str) or len(value) > 256:
            raise UnsupportedVersion("version must be a string of at most 256 characters")
        match = re.fullmatch(r"(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?(?:\.(0|[1-9]\d*))?(?:-([0-9A-Za-z.-]*))?(?:\+([^\s]+))?", value)
        if not match:
            raise UnsupportedVersion(f"unsupported numeric/semantic version: {value!r}")
        self.parts = tuple(int(p or 0) for p in match.groups()[:3])
        prerelease = match[4]
        if prerelease and any(not p or (p.isdigit() and len(p) > 1 and p[0] == '0') for p in prerelease.split('.')):
            raise UnsupportedVersion(f"invalid prerelease: {value!r}")
        self.pre = None if prerelease is None else tuple(prerelease.split('.')) if prerelease else ()

    def __eq__(self, other):
        return isinstance(other, Version) and (self.parts, self.pre) == (other.parts, other.pre)

    def __lt__(self, other):
        if self.parts != other.parts:
            return self.parts < other.parts
        if self.pre is None:
            return False
        if other.pre is None:
            return True
        for a, b in zip(self.pre, other.pre):
            if a == b:
                continue
            if a.isdigit() and b.isdigit():
                return int(a) < int(b)
            if a.isdigit() != b.isdigit():
                return a.isdigit()
            return a < b
        return len(self.pre) < len(other.pre)


def _compare(actual, op, expected):
    return {"=": actual == expected, ">": actual > expected, ">=": actual >= expected,
            "<": actual < expected, "<=": actual <= expected}[op]


def _fabric_atom(actual, expression):
    if expression in ("*", "x", "X"):
        return True
    match = re.fullmatch(r"(>=|<=|>|<|=|\^|~)?(.+)", expression)
    if not match:
        raise UnsupportedVersion(f"unsupported predicate: {expression!r}")
    op, value = match[1] or "=", match[2]
    if '*' in value or re.search(r"(?:^|\.)[xX](?:\.|$)", value):
        if op != "=" or not re.fullmatch(r"\d+(?:\.\d+)?\.(?:\*|x|X)", value):
            raise UnsupportedVersion(f"unsupported wildcard: {expression!r}")
        base = value.rsplit('.', 1)[0]
        lower = Version(base + '-')
        actual_v = Version(actual)
        index = len(base.split('.')) - 1
        upper = list(lower.parts)
        upper[index] += 1
        upper[index+1:] = [0] * (2-index)
        return lower <= actual_v < Version('.'.join(map(str, upper)) + '-')
    try:
        expected = Version(value)
    except UnsupportedVersion:
        if op == "=" and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", value):
            return actual == value
        raise
    actual_v = Version(actual)
    if op in ('^', '~'):
        upper = list(expected.parts)
        if op == '~':
            index = 0 if len(value.split('+')[0].split('-')[0].split('.')) == 1 else 1
        else:
            index = 0  # Fabric caret always advances major, including 0.x.
        upper[index] += 1
        upper[index+1:] = [0] * (2-index)
        return expected <= actual_v < Version('.'.join(map(str, upper)) + '-')
    return _compare(actual_v, op, expected)


def fabric_matches(actual, predicate):
    """Arrays are OR; whitespace-delimited comparisons are AND. Parse all branches."""
    alternatives = predicate if isinstance(predicate, list) else [predicate]
    if not alternatives or len(alternatives) > 128:
        raise UnsupportedVersion("predicate must have 1..128 alternatives")
    results = []
    for expression in alternatives:
        if not isinstance(expression, str) or not expression.strip() or len(expression) > 1024:
            raise UnsupportedVersion("predicate must be a nonempty string of at most 1024 characters")
        atoms = expression.split()
        # No short circuit: unknown branches never silently pass.
        results.append(all([_fabric_atom(actual, atom) for atom in atoms]))
    return any(results)


def maven_matches(actual, expression):
    """Numeric interval or exact subset; Maven unions/qualifier ordering fail closed."""
    if not isinstance(expression, str) or not expression or len(expression) > 1024:
        raise UnsupportedVersion("invalid Maven version range")
    if expression == '*':
        raise UnsupportedVersion("'*' is not a supported Maven version range")
    exact = re.fullmatch(r"\[([^,\[\]()]+)\]", expression)
    if exact:
        Version(actual); Version(exact[1])
        return actual == exact[1]
    interval = re.fullmatch(r"([\[(])([^,\[\]()]*)?,([^,\[\]()]*)?([\])])", expression)
    if not interval:
        raise UnsupportedVersion("only Maven numeric [exact] and one interval are supported")
    left, low, high, right = interval.groups()
    if not low and not high:
        raise UnsupportedVersion("unbounded empty Maven range")
    if (not low and left != '(') or (not high and right != ')'):
        raise UnsupportedVersion("unbounded Maven endpoints must be exclusive")
    values = [v for v in (actual, low, high) if v]
    if any(not re.fullmatch(r"\d+(?:\.\d+){0,2}", v) for v in values):
        raise UnsupportedVersion("Maven qualifier and extended-component ordering is unsupported")
    av = Version(actual)
    lv, hv = Version(low) if low else None, Version(high) if high else None
    if lv and hv and (lv > hv or (lv == hv and (left != '[' or right != ']'))):
        raise UnsupportedVersion("empty/reversed Maven interval")
    return (lv is None or _compare(av, '>=' if left == '[' else '>', lv)) and (hv is None or _compare(av, '<=' if right == ']' else '<', hv))


def matches(actual, predicate, dialect):
    return fabric_matches(actual, predicate) if dialect == 'fabric' else maven_matches(actual, predicate)
