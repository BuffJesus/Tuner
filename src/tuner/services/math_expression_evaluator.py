"""Evaluates TunerStudio/Speeduino formula output channel expressions.

Formula output channels come from lines of the form
``name = { expression } [, "units"] [, digits]`` inside the ``[OutputChannels]``
section of the INI. Parsing is handled upstream by
``IniParser._parse_output_channels`` and persisted on
``EcuDefinition.formula_output_channels``. This module is the **evaluator
half** (G4 Phase 2) — it takes a formula string plus a live channel snapshot
and returns a numeric value.

Grammar — superset of ``VisibilityExpressionService`` that adds arithmetic,
unary minus, C-style bit-shifts, and the ``? :`` ternary operator so the full
vocabulary used by the production Speeduino INI (~65 formulas) evaluates
correctly::

    expr     ::= ternary
    ternary  ::= or_expr ( '?' expr ':' expr )?
    or_expr  ::= and_expr ( '||' and_expr )*
    and_expr ::= not_expr ( '&&' not_expr )*
    not_expr ::= '!' not_expr | cmp_expr
    cmp_expr ::= shift ( cmp_op shift )?
    cmp_op   ::= '==' | '!=' | '>=' | '<=' | '>' | '<'
    shift    ::= add_expr ( ('<<' | '>>') add_expr )*
    add_expr ::= mul_expr ( ('+' | '-') mul_expr )*
    mul_expr ::= unary ( ('*' | '/' | '%') unary )*
    unary    ::= ('-' | '+') unary | atom
    atom     ::= '(' expr ')' | IDENT '(' arglist ')' | NUMBER | IDENT
    arglist  ::= (expr (',' expr)*)?

Semantics mirror ``VisibilityExpressionService``:

- Booleans are floats: ``0.0`` is false, anything else is true.
- Unknown identifiers default to ``0.0``.
- Division by zero returns ``0.0`` (fail-safe, never ``inf``/``nan``).
- Bit-shift operands are coerced to ``int`` before the shift, result is float.
- Any parse error returns ``0.0`` (fail-safe — a broken formula must not
  leak exceptions into the runtime poll tick).

The only supported function is ``arrayValue(arrayName, indexExpr)`` with the
same semantics as the visibility service (optional ``array.`` prefix, integer
truncation of the index, out-of-range returns ``0.0``).
"""
from __future__ import annotations

import re

from tuner.domain.ecu_definition import EcuDefinition, FormulaOutputChannel
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue


_TOKEN_RE = re.compile(
    r"(?P<NUMBER>\d+(?:\.\d+)?)"
    r"|(?P<OP><<|>>|==|!=|>=|<=|&&|\|\||[+\-*/%><!(),?:])"
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

    # -- expression levels -------------------------------------------------

    def parse_expr(self) -> float:
        return self._parse_ternary()

    def _parse_ternary(self) -> float:
        cond = self._parse_or()
        if self._peek() == "?":
            self._consume()
            then_val = self._parse_ternary()
            if self._peek() == ":":
                self._consume()
            else_val = self._parse_ternary()
            return then_val if cond != 0.0 else else_val
        return cond

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
        left = self._parse_shift()
        op = self._peek()
        if op in ("==", "!=", ">=", "<=", ">", "<"):
            self._consume()
            right = self._parse_shift()
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

    def _parse_shift(self) -> float:
        left = self._parse_add()
        while self._peek() in ("<<", ">>"):
            op = self._consume()
            right = self._parse_add()
            li = int(left)
            ri = int(right)
            if op == "<<":
                left = float(li << ri) if ri >= 0 else 0.0
            else:
                left = float(li >> ri) if ri >= 0 else 0.0
        return left

    def _parse_add(self) -> float:
        left = self._parse_mul()
        while self._peek() in ("+", "-"):
            op = self._consume()
            right = self._parse_mul()
            left = left + right if op == "+" else left - right
        return left

    def _parse_mul(self) -> float:
        left = self._parse_unary()
        while self._peek() in ("*", "/", "%"):
            op = self._consume()
            right = self._parse_unary()
            if op == "*":
                left = left * right
            elif op == "/":
                left = (left / right) if right != 0.0 else 0.0
            else:  # %
                left = (left % right) if right != 0.0 else 0.0
        return left

    def _parse_unary(self) -> float:
        tok = self._peek()
        if tok == "-":
            self._consume()
            return -self._parse_unary()
        if tok == "+":
            self._consume()
            return self._parse_unary()
        return self._parse_atom()

    def _parse_atom(self) -> float:
        token = self._peek()
        if token is None:
            return 0.0
        if token == "(":
            self._consume()
            val = self._parse_ternary()
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
        self._consume()  # consume '('
        if name == "arrayValue":
            return self._eval_array_value()
        # Unknown function — skip to matching ')' and return 0.0.
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
        array_name_token = self._peek()
        if array_name_token not in (None, ")", ","):
            self._consume()
        else:
            array_name_token = ""
        if self._peek() == ",":
            self._consume()
        index_val = self._parse_ternary()
        if self._peek() == ")":
            self._consume()

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


class MathExpressionEvaluator:
    """Evaluates TunerStudio-style formula output channel expressions.

    This is the evaluator half of G4 (virtual / formula output channels). The
    parser half lives in ``IniParser._parse_output_channels`` and persists
    results on ``EcuDefinition.formula_output_channels``.
    """

    def evaluate(
        self,
        expression: str | None,
        values: dict[str, float],
        arrays: dict[str, list[float]] | None = None,
    ) -> float:
        """Return the numeric value of *expression* against *values*.

        Parameters
        ----------
        expression:
            Raw expression string. The surrounding ``{ ... }`` braces (as
            persisted by the INI parser for visibility expressions) are
            accepted for symmetry with ``VisibilityExpressionService`` even
            though formula channels store the inner form on
            ``FormulaOutputChannel.formula_expression``.
        values:
            Current channel values keyed by channel name (live output
            channel snapshot plus any already-computed formula channels).
        arrays:
            Optional ``arrayValue(name, index)`` lookup table.

        Returns
        -------
        float
            The computed value, or ``0.0`` if *expression* is empty or a
            parse error occurs.
        """
        if not expression:
            return 0.0
        expr = expression.strip()
        if expr.startswith("{") and expr.endswith("}"):
            expr = expr[1:-1].strip()
        if not expr:
            return 0.0
        try:
            tokens = _tokenize(expr)
            parser = _Parser(tokens, values, arrays)
            return parser.parse_expr()
        except Exception:
            return 0.0

    def enrich_snapshot(
        self,
        snapshot: OutputChannelSnapshot,
        definition: EcuDefinition | None,
    ) -> OutputChannelSnapshot:
        """Return *snapshot* with formula output channels appended.

        The input snapshot is **not** mutated. Existing hardware channels
        are preserved in order; freshly-computed formula channels are
        appended after them, using ``FormulaOutputChannel.units`` as each
        computed entry's units.

        If *definition* is ``None`` or has no formula channels, the input
        snapshot is returned unchanged (same object — no copy). Runtime
        paths can call this unconditionally on every poll tick without
        paying an allocation when there are no formulas.

        The definition's ``output_channel_arrays`` map is passed through
        as the ``arrays`` argument to ``compute_all`` so formulas that
        reference ``arrayValue(array.name, index)`` can resolve cleanly.
        """
        if definition is None or not definition.formula_output_channels:
            return snapshot
        computed = self.compute_all(
            definition.formula_output_channels,
            snapshot.as_dict(),
            definition.output_channel_arrays or None,
        )
        units_by_name = {
            f.name: f.units for f in definition.formula_output_channels
        }
        appended = list(snapshot.values)
        for f in definition.formula_output_channels:
            appended.append(
                OutputChannelValue(
                    name=f.name,
                    value=computed[f.name],
                    units=units_by_name.get(f.name),
                )
            )
        return OutputChannelSnapshot(
            timestamp=snapshot.timestamp, values=appended
        )

    def compute_all(
        self,
        formulas: list[FormulaOutputChannel],
        values: dict[str, float],
        arrays: dict[str, list[float]] | None = None,
    ) -> dict[str, float]:
        """Compute every formula channel against *values* in declaration order.

        Each computed value is folded back into the working snapshot so
        later formulas can reference earlier ones (the production INI does
        this: ``cycleTime = revolutionTime * strokeMultipler`` depends on
        ``revolutionTime`` and ``strokeMultipler`` being computed first).

        The input *values* dict is **not** mutated. The returned dict
        contains only the freshly-computed formula channels.
        """
        working: dict[str, float] = dict(values)
        computed: dict[str, float] = {}
        for f in formulas:
            result = self.evaluate(f.formula_expression, working, arrays)
            computed[f.name] = result
            working[f.name] = result
        return computed
