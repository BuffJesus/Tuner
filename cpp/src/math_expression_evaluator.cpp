// SPDX-License-Identifier: MIT
//
// tuner_core::math_expression_evaluator implementation. Direct port of
// ``tuner.services.math_expression_evaluator`` — pure logic, stdlib only.

#include "tuner_core/math_expression_evaluator.hpp"

#include <cctype>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace tuner_core::math_expression_evaluator {

namespace {

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

// Token kinds mirror the Python regex:
//   NUMBER  → digits, optional '.' + digits
//   OP      → <<, >>, ==, !=, >=, <=, &&, ||, +, -, *, /, %, >, <, !,
//             (, ), ',', '?', ':'
//   IDENT   → [A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*
// Whitespace is dropped. Unrecognized characters are silently skipped.
std::vector<std::string> tokenize(std::string_view text) {
    std::vector<std::string> tokens;
    const std::size_t n = text.size();
    std::size_t i = 0;
    while (i < n) {
        const char c = text[i];
        if (std::isspace(static_cast<unsigned char>(c))) {
            ++i;
            continue;
        }
        // Number
        if (std::isdigit(static_cast<unsigned char>(c))) {
            std::size_t j = i;
            while (j < n && std::isdigit(static_cast<unsigned char>(text[j]))) ++j;
            if (j < n && text[j] == '.') {
                ++j;
                while (j < n && std::isdigit(static_cast<unsigned char>(text[j]))) ++j;
            }
            tokens.emplace_back(text.substr(i, j - i));
            i = j;
            continue;
        }
        // Two-char operators
        if (i + 1 < n) {
            const char d = text[i + 1];
            if ((c == '<' && d == '<') ||
                (c == '>' && d == '>') ||
                (c == '=' && d == '=') ||
                (c == '!' && d == '=') ||
                (c == '>' && d == '=') ||
                (c == '<' && d == '=') ||
                (c == '&' && d == '&') ||
                (c == '|' && d == '|')) {
                tokens.emplace_back(text.substr(i, 2));
                i += 2;
                continue;
            }
        }
        // Single-char operators
        if (c == '+' || c == '-' || c == '*' || c == '/' || c == '%' ||
            c == '>' || c == '<' || c == '!' ||
            c == '(' || c == ')' || c == ',' ||
            c == '?' || c == ':') {
            tokens.emplace_back(1, c);
            ++i;
            continue;
        }
        // Identifier (with optional `.IDENT` segments)
        if (std::isalpha(static_cast<unsigned char>(c)) || c == '_') {
            std::size_t j = i;
            auto consume_word = [&]() {
                while (j < n) {
                    char k = text[j];
                    if (std::isalnum(static_cast<unsigned char>(k)) || k == '_') {
                        ++j;
                    } else {
                        break;
                    }
                }
            };
            consume_word();
            while (j + 1 < n && text[j] == '.' &&
                   (std::isalpha(static_cast<unsigned char>(text[j + 1])) ||
                    text[j + 1] == '_')) {
                ++j;
                consume_word();
            }
            tokens.emplace_back(text.substr(i, j - i));
            i = j;
            continue;
        }
        // Unrecognized — skip silently (mirrors Python finditer).
        ++i;
    }
    return tokens;
}

// ---------------------------------------------------------------------------
// Parser
// ---------------------------------------------------------------------------

class Parser {
public:
    Parser(const std::vector<std::string>& tokens,
           const ValueMap& values,
           const ArrayMap* arrays)
        : tokens_(tokens), pos_(0), values_(values), arrays_(arrays) {}

    double parse_expr() { return parse_ternary(); }

private:
    const std::vector<std::string>& tokens_;
    std::size_t pos_;
    const ValueMap& values_;
    const ArrayMap* arrays_;

    const std::string* peek() const {
        return pos_ < tokens_.size() ? &tokens_[pos_] : nullptr;
    }
    const std::string& consume() { return tokens_[pos_++]; }

    bool peek_is(const char* s) const {
        const auto* p = peek();
        return p != nullptr && *p == s;
    }

    double parse_ternary() {
        double cond = parse_or();
        if (peek_is("?")) {
            consume();
            double then_val = parse_ternary();
            if (peek_is(":")) consume();
            double else_val = parse_ternary();
            return cond != 0.0 ? then_val : else_val;
        }
        return cond;
    }

    double parse_or() {
        double left = parse_and();
        while (peek_is("||")) {
            consume();
            double right = parse_and();
            left = (left != 0.0 || right != 0.0) ? 1.0 : 0.0;
        }
        return left;
    }

    double parse_and() {
        double left = parse_not();
        while (peek_is("&&")) {
            consume();
            double right = parse_not();
            left = (left != 0.0 && right != 0.0) ? 1.0 : 0.0;
        }
        return left;
    }

    double parse_not() {
        if (peek_is("!")) {
            consume();
            double v = parse_not();
            return v != 0.0 ? 0.0 : 1.0;
        }
        return parse_cmp();
    }

    double parse_cmp() {
        double left = parse_shift();
        const auto* op = peek();
        if (op != nullptr) {
            const std::string& s = *op;
            if (s == "==" || s == "!=" || s == ">=" || s == "<=" ||
                s == ">"  || s == "<") {
                std::string opcopy = s;
                consume();
                double right = parse_shift();
                if (opcopy == "==") return left == right ? 1.0 : 0.0;
                if (opcopy == "!=") return left != right ? 1.0 : 0.0;
                if (opcopy == ">")  return left >  right ? 1.0 : 0.0;
                if (opcopy == "<")  return left <  right ? 1.0 : 0.0;
                if (opcopy == ">=") return left >= right ? 1.0 : 0.0;
                if (opcopy == "<=") return left <= right ? 1.0 : 0.0;
            }
        }
        return left;
    }

    double parse_shift() {
        double left = parse_add();
        while (peek_is("<<") || peek_is(">>")) {
            std::string op = consume();
            double right = parse_add();
            auto li = static_cast<std::int64_t>(left);
            auto ri = static_cast<std::int64_t>(right);
            if (ri < 0) {
                left = 0.0;
            } else if (op == "<<") {
                left = static_cast<double>(li << ri);
            } else {
                left = static_cast<double>(li >> ri);
            }
        }
        return left;
    }

    double parse_add() {
        double left = parse_mul();
        while (peek_is("+") || peek_is("-")) {
            std::string op = consume();
            double right = parse_mul();
            left = (op == "+") ? left + right : left - right;
        }
        return left;
    }

    double parse_mul() {
        double left = parse_unary();
        while (peek_is("*") || peek_is("/") || peek_is("%")) {
            std::string op = consume();
            double right = parse_unary();
            if (op == "*") {
                left = left * right;
            } else if (op == "/") {
                left = (right != 0.0) ? left / right : 0.0;
            } else {
                left = (right != 0.0) ? std::fmod(left, right) : 0.0;
            }
        }
        return left;
    }

    double parse_unary() {
        if (peek_is("-")) {
            consume();
            return -parse_unary();
        }
        if (peek_is("+")) {
            consume();
            return parse_unary();
        }
        return parse_atom();
    }

    double parse_atom() {
        const auto* tok = peek();
        if (tok == nullptr) return 0.0;
        if (*tok == "(") {
            consume();
            double v = parse_ternary();
            if (peek_is(")")) consume();
            return v;
        }
        std::string token = consume();
        if (peek_is("(")) {
            return call_function(token);
        }
        try {
            std::size_t consumed = 0;
            double v = std::stod(token, &consumed);
            if (consumed == token.size()) return v;
        } catch (...) {
            // fall through
        }
        auto it = values_.find(token);
        return it != values_.end() ? it->second : 0.0;
    }

    double call_function(const std::string& name) {
        consume();  // consume '('
        if (name == "arrayValue") return eval_array_value();
        // Unknown function — skip to matching ')' and return 0.0.
        int depth = 1;
        while (peek() != nullptr && depth > 0) {
            const std::string& tok = consume();
            if (tok == "(") ++depth;
            else if (tok == ")") --depth;
        }
        return 0.0;
    }

    double eval_array_value() {
        std::string array_name;
        const auto* tok = peek();
        if (tok != nullptr && *tok != ")" && *tok != ",") {
            array_name = consume();
        }
        if (peek_is(",")) consume();
        double index_val = parse_ternary();
        if (peek_is(")")) consume();

        std::string name = array_name;
        const std::string prefix = "array.";
        if (name.rfind(prefix, 0) == 0) name = name.substr(prefix.size());
        if (name.empty() || arrays_ == nullptr) return 0.0;
        auto it = arrays_->find(name);
        if (it == arrays_->end()) return 0.0;
        const auto& arr = it->second;
        auto index = static_cast<std::int64_t>(index_val);
        if (index >= 0 &&
            static_cast<std::size_t>(index) < arr.size()) {
            return arr[static_cast<std::size_t>(index)];
        }
        return 0.0;
    }
};

std::string_view strip(std::string_view s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
        s.remove_prefix(1);
    }
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
        s.remove_suffix(1);
    }
    return s;
}

}  // namespace

double evaluate(
    std::string_view expression,
    const ValueMap& values,
    const ArrayMap* arrays) {
    if (expression.empty()) return 0.0;
    auto trimmed = strip(expression);
    if (trimmed.size() >= 2 && trimmed.front() == '{' && trimmed.back() == '}') {
        trimmed = strip(trimmed.substr(1, trimmed.size() - 2));
    }
    if (trimmed.empty()) return 0.0;

    try {
        auto tokens = tokenize(trimmed);
        Parser parser(tokens, values, arrays);
        return parser.parse_expr();
    } catch (...) {
        return 0.0;
    }
}

ValueMap compute_all(
    const std::vector<IniFormulaOutputChannel>& formulas,
    const ValueMap& values,
    const ArrayMap* arrays) {
    ValueMap working = values;
    ValueMap computed;
    for (const auto& f : formulas) {
        double result = evaluate(f.formula_expression, working, arrays);
        computed[f.name] = result;
        working[f.name] = result;
    }
    return computed;
}

void enrich(
    ValueMap& working,
    const std::vector<IniFormulaOutputChannel>& formulas,
    const ArrayMap* arrays) {
    for (const auto& f : formulas) {
        if (working.find(f.name) != working.end()) {
            // Hardware channel with the same name wins — don't clobber.
            continue;
        }
        working[f.name] = evaluate(f.formula_expression, working, arrays);
    }
}

}  // namespace tuner_core::math_expression_evaluator
