"""Evaluates TunerStudio/Speeduino INI visibility expressions.

Expressions are stored in the INI (and in domain snapshots) as ``{expr}``; the
surrounding braces are preserved in the stored string and stripped here before
evaluation.

Supported grammar
-----------------
::

    expr     ::= or_expr
    or_expr  ::= and_expr ( '||' and_expr )*
    and_expr ::= not_expr ( '&&' not_expr )*
    not_expr ::= '!' not_expr | cmp_expr
    cmp_expr ::= atom ( op atom )?
    op       ::= '==' | '!=' | '>=' | '<=' | '>' | '<'
    atom     ::= '(' expr ')' | IDENT '(' arglist ')' | NUMBER | IDENT
    arglist  ::= (atom (',' atom)*)?

Booleans are represented as floats: ``0.0`` is false, anything else is true.
Unknown identifiers default to ``0.0``.  Any parse error returns ``True``
(fail-open — never hide content because of a bad expression).

Supported functions
-------------------
``arrayValue(arrayName, indexExpr)``
    Look up ``arrayName`` (with or without an ``array.`` prefix) at the integer
    position given by *indexExpr*.  Returns ``0.0`` when the array is unknown,
    the index is out of range, or no array data was supplied to the evaluator.
"""
from __future__ import annotations

import re


_TOKEN_RE = re.compile(
    r"(?P<NUMBER>\d+(?:\.\d+)?)"
    r"|(?P<OP>==|!=|>=|<=|&&|\|\||[><!(),])"
    r"|(?P<IDENT>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)"
    r"|(?P<WS>\s+)"
)


def _tokenize(text: str) -> list[str]:
    return [m.group() for m in _TOKEN_RE.finditer(text) if m.lastgroup != "WS"]


class _Parser:
    __slots__ = ("_tokens", "_pos", "_values", "_arrays")

    def __init__(
        self,
        tokens: list[str],
        values: dict[str, float],
        arrays: dict[str, list[float]] | None,
    ) -> None:
        self._tokens = tokens
        self._pos = 0
        self._values = values
        self._arrays = arrays

    def _peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _consume(self) -> str:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def parse_expr(self) -> float:
        return self._parse_or()

    def _parse_or(self) -> float:
        left = self._parse_and()
        while self._peek() == "||":
            self._consume()
            right = self._parse_and()
            left = 1.0 if (left or right) else 0.0
        return left

    def _parse_and(self) -> float:
        left = self._parse_not()
        while self._peek() == "&&":
            self._consume()
            right = self._parse_not()
            left = 1.0 if (left and right) else 0.0
        return left

    def _parse_not(self) -> float:
        if self._peek() == "!":
            self._consume()
            val = self._parse_not()
            return 0.0 if val else 1.0
        return self._parse_cmp()

    def _parse_cmp(self) -> float:
        left = self._parse_atom()
        op = self._peek()
        if op in ("==", "!=", ">=", "<=", ">", "<"):
            self._consume()
            right = self._parse_atom()
            if op == "==":
                return 1.0 if left == right else 0.0
            if op == "!=":
                return 1.0 if left != right else 0.0
            if op == ">":
                return 1.0 if left > right else 0.0
            if op == "<":
                return 1.0 if left < right else 0.0
            if op == ">=":
                return 1.0 if left >= right else 0.0
            if op == "<=":
                return 1.0 if left <= right else 0.0
        return left

    def _parse_atom(self) -> float:
        token = self._peek()
        if token is None:
            return 0.0
        if token == "(":
            self._consume()
            val = self._parse_or()
            if self._peek() == ")":
                self._consume()
            return val
        self._consume()
        # Function call?
        if self._peek() == "(":
            return self._call_function(token)
        try:
            return float(token)
        except ValueError:
            return float(self._values.get(token, 0.0))

    def _call_function(self, name: str) -> float:
        """Dispatch a function call starting right after the function name."""
        self._consume()  # consume '('
        if name == "arrayValue":
            return self._eval_array_value()
        # Unknown function — skip all arguments and return 0.0 (fail-safe)
        depth = 1
        while self._peek() is not None and depth > 0:
            tok = self._consume()
            if tok == "(":
                depth += 1
            elif tok == ")":
                depth -= 1
        return 0.0

    def _eval_array_value(self) -> float:
        """Evaluate arrayValue(arrayName, indexExpr) — already consumed '('."""
        # First argument: array name identifier (NOT a value expression)
        array_name_token = self._peek()
        if array_name_token not in (None, ")", ","):
            self._consume()
        else:
            array_name_token = ""
        if self._peek() == ",":
            self._consume()
        # Second argument: index expression
        index_val = self._parse_or()
        if self._peek() == ")":
            self._consume()

        # Strip the "array." namespace prefix used in INI visibility expressions
        name = (array_name_token or "").strip()
        if name.startswith("array."):
            name = name[len("array."):]
        if not name or self._arrays is None:
            return 0.0
        arr = self._arrays.get(name)
        if arr is None:
            return 0.0
        index = int(index_val)
        if 0 <= index < len(arr):
            return float(arr[index])
        return 0.0


class VisibilityExpressionService:
    """Evaluates TunerStudio-style visibility expressions against current tune values."""

    def evaluate(
        self,
        expression: str | None,
        values: dict[str, float],
        arrays: dict[str, list[float]] | None = None,
    ) -> bool:
        """Return ``True`` if *expression* is satisfied (or absent).

        Parameters
        ----------
        expression:
            Raw expression string, e.g. ``"{fuelAlgorithm == 1}"`` or ``None``.
        values:
            Current scalar parameter values keyed by parameter name.
        arrays:
            Optional mapping of array names to their value lists.  Used to
            resolve ``arrayValue(name, index)`` function calls.  When ``None``,
            ``arrayValue()`` always returns ``0.0`` (fail-closed for unknown
            boards).

        Returns
        -------
        bool
            ``True`` when the expression evaluates to a non-zero value, when
            *expression* is ``None`` or empty, or when a parse error occurs.
        """
        if not expression:
            return True
        expr = expression.strip()
        if expr.startswith("{") and expr.endswith("}"):
            expr = expr[1:-1].strip()
        if not expr:
            return True
        try:
            tokens = _tokenize(expr)
            parser = _Parser(tokens, values, arrays)
            result = parser.parse_expr()
            return result != 0.0
        except Exception:
            return True
