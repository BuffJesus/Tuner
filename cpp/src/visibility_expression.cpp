// SPDX-License-Identifier: MIT
//
// tuner_core::visibility_expression implementation. Direct port of
// `tuner.services.visibility_expression_service` — pure logic.

#include "tuner_core/visibility_expression.hpp"

#include <cctype>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace tuner_core::visibility_expression {

namespace {

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

// Token kinds match the Python regex:
//   NUMBER  → digits, optionally followed by '.' and more digits
//   OP      → ==, !=, >=, <=, &&, ||, >, <, !, (, ), ,
//   IDENT   → [A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*  — dotted identifiers allowed
// Whitespace is dropped. Anything else is silently skipped (Python's
// regex finditer behaviour for unmatchable characters).
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
            if ((c == '=' && d == '=') ||
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
        if (c == '>' || c == '<' || c == '!' ||
            c == '(' || c == ')' || c == ',') {
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
            // Optional `.word` segments — must be followed by an
            // identifier-start char to count as part of the identifier.
            while (j + 1 < n && text[j] == '.' &&
                   (std::isalpha(static_cast<unsigned char>(text[j + 1])) ||
                    text[j + 1] == '_')) {
                ++j;  // consume '.'
                consume_word();
            }
            tokens.emplace_back(text.substr(i, j - i));
            i = j;
            continue;
        }
        // Unrecognized character — skip silently to mirror Python's
        // `finditer` behaviour (it just doesn't match).
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

    double parse_expr() { return parse_or(); }

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
        double left = parse_atom();
        const auto* op = peek();
        if (op != nullptr) {
            const std::string& s = *op;
            if (s == "==" || s == "!=" || s == ">=" || s == "<=" ||
                s == ">"  || s == "<") {
                std::string opcopy = s;
                consume();
                double right = parse_atom();
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

    double parse_atom() {
        const auto* tok = peek();
        if (tok == nullptr) return 0.0;
        if (*tok == "(") {
            consume();
            double v = parse_or();
            if (peek_is(")")) consume();
            return v;
        }
        std::string token = consume();
        if (peek_is("(")) {
            return call_function(token);
        }
        // Try to parse as a number; on failure, look up as an identifier.
        try {
            std::size_t consumed = 0;
            double v = std::stod(token, &consumed);
            if (consumed == token.size()) return v;
        } catch (...) {
            // fall through to identifier lookup
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
        // First argument: array name as a literal identifier.
        std::string array_name;
        const auto* tok = peek();
        if (tok != nullptr && *tok != ")" && *tok != ",") {
            array_name = consume();
        }
        if (peek_is(",")) consume();
        // Second argument: index expression.
        double index_val = parse_or();
        if (peek_is(")")) consume();

        // Strip the `array.` namespace prefix.
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

}  // namespace

bool evaluate(
    std::string_view expression,
    const ValueMap& values,
    const ArrayMap* arrays) {
    if (expression.empty()) return true;
    // Strip surrounding whitespace, then `{ ... }` braces, then
    // whitespace again — mirrors the Python `expr.strip()` →
    // `expr[1:-1].strip()` chain.
    auto strip = [](std::string_view s) {
        while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
            s.remove_prefix(1);
        }
        while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
            s.remove_suffix(1);
        }
        return s;
    };
    auto trimmed = strip(expression);
    if (trimmed.size() >= 2 && trimmed.front() == '{' && trimmed.back() == '}') {
        trimmed = strip(trimmed.substr(1, trimmed.size() - 2));
    }
    if (trimmed.empty()) return true;

    try {
        auto tokens = tokenize(trimmed);
        Parser parser(tokens, values, arrays);
        double result = parser.parse_expr();
        return result != 0.0;
    } catch (...) {
        // Fail-open: never hide content because of a bad expression.
        return true;
    }
}

}  // namespace tuner_core::visibility_expression
