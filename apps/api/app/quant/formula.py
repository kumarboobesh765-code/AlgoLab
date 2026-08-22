"""Safe formula engine.

Evaluates arithmetic expressions over per-bar series without ever touching
`eval`/`exec`. Grammar (whitespace ignored):

    expr   := term (('+' | '-') term)*
    term   := factor (('*' | '/' | '%') factor)*
    factor := unary ('^' factor)?            # right-associative power
    unary  := ('-' | '+')? primary
    primary:= NUMBER | IDENT | FUNC '(' args ')' | '(' expr ')'

Identifiers resolve from the evaluation environment (price fields, indicator
outputs, strategy variables). Unknown identifiers raise `FormulaError`.
Division/modulo by zero yields NaN for that bar instead of crashing a run.
"""

import math
from collections.abc import Callable, Sequence

NAN = math.nan

FUNCTIONS: dict[str, Callable] = {
    "abs": 1,
    "min": 2,
    "max": 2,
    "sqrt": 1,
    "log": 1,
    "round": 1,
}


class FormulaError(ValueError):
    """Raised for any tokenizing, parsing or resolution failure."""


# ------------------------------------------------------------------ tokens


def _tokenize(text: str) -> list[tuple[str, object]]:
    tokens: list[tuple[str, object]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            start = i
            while i < n and (text[i].isdigit() or text[i] == "."):
                i += 1
            literal = text[start:i]
            try:
                value = float(literal)
            except ValueError as exc:
                raise FormulaError(f"Invalid number {literal!r}") from exc
            tokens.append(("num", value))
        elif ch.isalpha() or ch == "_":
            start = i
            while i < n and (text[i].isalnum() or text[i] in "_."):
                i += 1
            name = text[start:i]
            if name.startswith(".") or name.endswith(".") or ".." in name:
                raise FormulaError(f"Malformed identifier {name!r}")
            if name in ("True", "False", "None", "and", "or", "not", "lambda"):
                raise FormulaError(f"Keyword {name!r} is not allowed in formulas")
            tokens.append(("ident", name))
        elif ch in "+-*/%^(),":
            tokens.append(("op", ch))
            i += 1
        else:
            raise FormulaError(f"Unexpected character {ch!r} at position {i}")
    tokens.append(("end", None))
    return tokens


# -------------------------------------------------------------------- AST
# Nodes are tuples: ("num", v) | ("var", name) | ("call", name, args)
#                  | ("unary", op, node) | ("bin", op, left, right)


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos]

    def next(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect_op(self, op: str):
        kind, value = self.next()
        if kind != "op" or value != op:
            raise FormulaError(f"Expected {op!r}, got {value!r}")

    def parse(self):
        node = self.expr()
        kind, value = self.peek()
        if kind != "end":
            raise FormulaError(f"Unexpected trailing input at {value!r}")
        return node

    def expr(self):
        node = self.term()
        while self.peek() == ("op", "+") or self.peek() == ("op", "-"):
            _, op = self.next()
            node = ("bin", op, node, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.peek() in (("op", "*"), ("op", "/"), ("op", "%")):
            _, op = self.next()
            node = ("bin", op, node, self.factor())
        return node

    def factor(self):
        node = self.unary()
        if self.peek() == ("op", "^"):
            self.next()
            return ("bin", "^", node, self.factor())
        return node

    def unary(self):
        if self.peek() in (("op", "-"), ("op", "+")):
            _, op = self.next()
            return ("unary", op, self.unary())
        return self.primary()

    def primary(self):
        kind, value = self.next()
        if kind == "num":
            return ("num", value)
        if kind == "ident":
            if self.peek() == ("op", "("):
                if value not in FUNCTIONS:
                    raise FormulaError(f"Unknown function {value!r}")
                self.expect_op("(")
                args = [self.expr()]
                arity = FUNCTIONS[value]
                while self.peek() == ("op", ","):
                    self.next()
                    args.append(self.expr())
                self.expect_op(")")
                if len(args) != arity:
                    raise FormulaError(
                        f"{value}() takes {arity} argument(s), got {len(args)}"
                    )
                return ("call", value, args)
            return ("var", value)
        if kind == "op" and value == "(":
            node = self.expr()
            self.expect_op(")")
            return node
        raise FormulaError(f"Unexpected token {value!r}")


def parse_formula(text: str) -> tuple:
    """Parse a formula into an AST. Raises FormulaError on bad input."""
    if not isinstance(text, str) or not text.strip():
        raise FormulaError("Formula must be a non-empty string")
    if len(text) > 500:
        raise FormulaError("Formula too long (max 500 chars)")
    return _Parser(_tokenize(text)).parse()


# --------------------------------------------------------------- evaluate


def _resolve(name: str, env: dict[str, Sequence[float]], length: int) -> list[float]:
    series = env.get(name)
    if series is None:
        known = ", ".join(sorted(env)) or "(nothing)"
        raise FormulaError(f"Unknown identifier {name!r}. Available: {known}")
    if len(series) != length:
        raise FormulaError(
            f"Identifier {name!r} has length {len(series)}, expected {length}"
        )
    return list(series)


def _apply_scalar(fn, values: list[float]) -> list[float]:
    out = []
    for v in values:
        try:
            result = fn(v)
        except (ValueError, OverflowError, ZeroDivisionError):
            result = NAN
        out.append(result)
    return out


def _eval_node(node: tuple, env: dict[str, Sequence[float]], length: int) -> list[float]:
    kind = node[0]

    if kind == "num":
        return [float(node[1])] * length

    if kind == "var":
        return _resolve(node[1], env, length)

    if kind == "unary":
        values = _eval_node(node[2], env, length)
        if node[1] == "-":
            return [-v for v in values]
        return values

    if kind == "call":
        fname, arg_nodes = node[1], node[2]
        args = [_eval_node(a, env, length) for a in arg_nodes]
        if fname == "abs":
            return [abs(v) for v in args[0]]
        if fname == "min":
            return [min(a, b) for a, b in zip(args[0], args[1], strict=True)]
        if fname == "max":
            return [max(a, b) for a, b in zip(args[0], args[1], strict=True)]
        if fname == "sqrt":
            return _apply_scalar(lambda v: math.sqrt(v) if v >= 0 else NAN, args[0])
        if fname == "log":
            return _apply_scalar(lambda v: math.log(v) if v > 0 else NAN, args[0])
        if fname == "round":
            return _apply_scalar(lambda v: float(round(v)), args[0])
        raise FormulaError(f"Unknown function {fname!r}")

    if kind == "bin":
        op = node[1]
        left = _eval_node(node[2], env, length)
        right = _eval_node(node[3], env, length)
        out: list[float] = []
        for a, b in zip(left, right, strict=True):
            if math.isnan(a) or math.isnan(b):
                out.append(NAN)
                continue
            try:
                if op == "+":
                    out.append(a + b)
                elif op == "-":
                    out.append(a - b)
                elif op == "*":
                    out.append(a * b)
                elif op == "/":
                    out.append(a / b if b != 0 else NAN)
                elif op == "%":
                    out.append(math.fmod(a, b) if b != 0 else NAN)
                elif op == "^":
                    result = math.pow(a, b)
                    out.append(result)
                else:
                    raise FormulaError(f"Unknown operator {op!r}")
            except (OverflowError, ValueError):
                out.append(NAN)
        return out

    raise FormulaError(f"Malformed AST node {kind!r}")


def evaluate_formula(ast: tuple, env: dict[str, Sequence[float]], length: int) -> list[float]:
    """Evaluate a parsed formula against the environment (series of `length`)."""
    return _eval_node(ast, env, length)


def compile_and_evaluate(
    text: str, env: dict[str, Sequence[float]], length: int
) -> list[float]:
    return evaluate_formula(parse_formula(text), env, length)
