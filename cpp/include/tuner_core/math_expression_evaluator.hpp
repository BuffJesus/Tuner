// SPDX-License-Identifier: MIT
//
// tuner_core::math_expression_evaluator — evaluator half of G4 (virtual /
// formula output channels). Direct port of
// ``tuner.services.math_expression_evaluator.MathExpressionEvaluator``.
//
// Grammar — superset of ``visibility_expression`` that adds arithmetic,
// unary minus, C-style bit-shifts, and the ``? :`` ternary operator so the
// full vocabulary used by the production Speeduino INI (~65 formulas)
// evaluates correctly::
//
//     expr     ::= ternary
//     ternary  ::= or_expr ( '?' expr ':' expr )?
//     or_expr  ::= and_expr ( '||' and_expr )*
//     and_expr ::= not_expr ( '&&' not_expr )*
//     not_expr ::= '!' not_expr | cmp_expr
//     cmp_expr ::= shift ( cmp_op shift )?
//     cmp_op   ::= '==' | '!=' | '>=' | '<=' | '>' | '<'
//     shift    ::= add_expr ( ('<<' | '>>') add_expr )*
//     add_expr ::= mul_expr ( ('+' | '-') mul_expr )*
//     mul_expr ::= unary ( ('*' | '/' | '%') unary )*
//     unary    ::= ('-' | '+') unary | atom
//     atom     ::= '(' expr ')' | IDENT '(' arglist ')' | NUMBER | IDENT
//
// Semantics:
//   - Booleans are doubles: 0.0 = false, anything else = true.
//   - Unknown identifiers default to 0.0.
//   - Division by zero returns 0.0 (fail-safe).
//   - Bit-shift operands are truncated to int64 first.
//   - Any parse error returns 0.0 (fail-safe).
//   - The only supported function is `arrayValue(arrayName, indexExpr)`.

#pragma once

#include "tuner_core/ini_output_channels_parser.hpp"

#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::math_expression_evaluator {

using ValueMap = std::map<std::string, double>;
using ArrayMap = std::map<std::string, std::vector<double>>;

// Evaluate a single expression. Accepts the inner form
// (``coolantRaw - 40``) or the braced form (``{ coolantRaw - 40 }``) for
// symmetry with the visibility-expression service.
double evaluate(
    std::string_view expression,
    const ValueMap& values,
    const ArrayMap* arrays = nullptr);

// Compute every formula channel against *values* in declaration order.
// Each computed value is folded back into the working snapshot so later
// formulas can reference earlier ones (the production INI does this:
// ``cycleTime = revolutionTime * strokeMultipler``).
//
// The input *values* map is not mutated. The returned map contains only
// the freshly-computed formula channels.
ValueMap compute_all(
    const std::vector<IniFormulaOutputChannel>& formulas,
    const ValueMap& values,
    const ArrayMap* arrays = nullptr);

// In-place variant: compute every formula channel and insert the results
// directly into *working*. Mirrors `MathExpressionEvaluator.enrich_snapshot`
// on the Python side — call this from the runtime poll tick with the
// mutable channel snapshot so downstream gauge/dashboard/logging code
// sees the computed channels alongside the hardware channels without any
// per-consumer wiring.
//
// Existing entries in *working* are not overwritten, so a formula channel
// that happens to share a name with a hardware channel (which is a bug
// in the INI and not something the production Speeduino INI does) is
// dropped silently rather than clobbering the hardware reading. No-op
// when *formulas* is empty.
void enrich(
    ValueMap& working,
    const std::vector<IniFormulaOutputChannel>& formulas,
    const ArrayMap* arrays = nullptr);

}  // namespace tuner_core::math_expression_evaluator
