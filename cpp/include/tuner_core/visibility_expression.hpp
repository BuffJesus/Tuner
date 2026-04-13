// SPDX-License-Identifier: MIT
//
// tuner_core::visibility_expression — port of the Python
// `VisibilityExpressionService`. Pure-logic evaluator for the small
// boolean expression language used by TunerStudio/Speeduino INI
// `field = ..., { expr }` visibility clauses. First sub-slice of the
// Phase 14 workspace-services port (Slice 4).
//
// Grammar (mirrors the Python docstring exactly)::
//
//     expr     ::= or_expr
//     or_expr  ::= and_expr ( '||' and_expr )*
//     and_expr ::= not_expr ( '&&' not_expr )*
//     not_expr ::= '!' not_expr | cmp_expr
//     cmp_expr ::= atom ( op atom )?
//     op       ::= '==' | '!=' | '>=' | '<=' | '>' | '<'
//     atom     ::= '(' expr ')' | IDENT '(' arglist ')' | NUMBER | IDENT
//     arglist  ::= (atom (',' atom)*)?
//
// Booleans are floats: 0.0 = false, anything else = true. Unknown
// identifiers default to 0.0. **Any parse error returns true** —
// fail-open, never hide content because of a bad expression. The
// only supported function is `arrayValue(arrayName, indexExpr)`.

#pragma once

#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::visibility_expression {

// Lookup tables passed by the caller. Both maps are by-name, exactly
// matching the Python signature `evaluate(expression, values, arrays)`.
using ValueMap = std::map<std::string, double>;
using ArrayMap = std::map<std::string, std::vector<double>>;

// Evaluate `expression` against `values` (and optional `arrays`).
// Returns `true` when the expression evaluates to a non-zero value,
// when `expression` is empty, or when a parse error occurs (fail-open).
//
// `expression` may carry surrounding `{ ... }` braces (as the INI
// stores them) — they're stripped here before tokenization.
bool evaluate(
    std::string_view expression,
    const ValueMap& values,
    const ArrayMap* arrays = nullptr);

}  // namespace tuner_core::visibility_expression
