"""A deliberately finite propositional language; never evaluates Python code."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Expr:
    op: str
    args: tuple["Expr", ...] = ()
    name: str = ""

    def evaluate(self, values: dict[str, bool]) -> bool:
        if self.op == "var":
            return values[self.name]
        if self.op in ("true", "false"):
            return self.op == "true"
        a = self.args[0].evaluate(values)
        if self.op == "!":
            return not a
        b = self.args[1].evaluate(values)
        return {"&&": a and b, "||": a or b, "^": a != b,
                "->": not a or b, "<->": a == b}[self.op]

    def variables(self) -> frozenset[str]:
        if self.op == "var":
            return frozenset([self.name])
        return frozenset().union(*(arg.variables() for arg in self.args))

    def size(self) -> int:
        return 1 + sum(arg.size() for arg in self.args)

    def __str__(self) -> str:
        if self.op == "var":
            return self.name
        if not self.args:
            return self.op
        if self.op == "!":
            return f"!({self.args[0]})"
        return f"({self.args[0]} {self.op} {self.args[1]})"


TOKEN = re.compile(r"\s*(<->|->|&&|\|\||[!^()]|[A-Za-z][A-Za-z0-9_]*)")
PRECEDENCE = {"<->": 1, "->": 2, "||": 3, "^": 4, "&&": 5}


def parse(source: str, variables: tuple[str, ...] | None = None) -> Expr:
    if not isinstance(source, str) or not source.strip() or len(source) > 4096:
        raise ValueError("formula must be nonempty text of at most 4096 characters")
    tokens, offset = [], 0
    source = source.strip()
    while offset < len(source):
        match = TOKEN.match(source, offset)
        if not match:
            raise ValueError(f"unsupported formula syntax at offset {offset}")
        tokens.append(match.group(1))
        offset = match.end()
    if len(tokens) > 512:
        raise ValueError("formula exceeds 512 tokens")
    cursor = 0

    def expression(minimum: int = 0, depth: int = 0) -> Expr:
        nonlocal cursor
        if depth > 32 or cursor >= len(tokens):
            raise ValueError("formula too deep or incomplete")
        token = tokens[cursor]
        cursor += 1
        if token == "!":
            left = Expr("!", (expression(6, depth + 1),))
        elif token == "(":
            left = expression(0, depth + 1)
            if cursor >= len(tokens) or tokens[cursor] != ")":
                raise ValueError("missing closing parenthesis")
            cursor += 1
        elif token in ("true", "false"):
            left = Expr(token)
        elif re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", token):
            left = Expr("var", name=token)
        else:
            raise ValueError(f"unexpected token {token!r}")
        while cursor < len(tokens) and tokens[cursor] in PRECEDENCE:
            operator = tokens[cursor]
            priority = PRECEDENCE[operator]
            if priority < minimum:
                break
            cursor += 1
            # Implication is right associative; all other binary operators are left associative.
            right = expression(priority if operator == "->" else priority + 1, depth + 1)
            left = Expr(operator, (left, right))
        return left

    result = expression()
    if cursor != len(tokens):
        raise ValueError(f"unexpected token {tokens[cursor]!r}")
    if variables is not None and result.variables() - set(variables):
        raise ValueError(f"undeclared variables: {sorted(result.variables() - set(variables))}")
    return result


def mutations(expr: Expr, variables: tuple[str, ...]) -> tuple[Expr, ...]:
    """Local typed edits. They generate hypotheses, never correctness evidence."""
    edits = {Expr("!", (expr,)), Expr("true"), Expr("false")}
    if expr.op == "var":
        edits.update(Expr("var", name=name) for name in variables)
    elif expr.op == "!":
        edits.add(expr.args[0])
    elif len(expr.args) == 2:
        edits.update(Expr(op, expr.args) for op in PRECEDENCE)
        edits.update(expr.args)
        edits.add(Expr(expr.op, tuple(reversed(expr.args))))
    for index, arg in enumerate(expr.args):
        for replacement in mutations(arg, variables):
            args = list(expr.args)
            args[index] = replacement
            edits.add(Expr(expr.op, tuple(args)))
    edits.discard(expr)
    return tuple(sorted((e for e in edits if e.size() <= 63), key=str))


def tau_formula(expr: Expr, streams: dict[str, str], algebra: str = "bv[1]") -> str:
    if algebra not in ("bv[1]", "sbf"):
        raise ValueError("export supports only bv[1] or explicitly restricted sbf")
    if expr.op == "var":
        one = "{1}:bv[1]" if algebra == "bv[1]" else "1:sbf"
        return f"({streams[expr.name]}[t]:{algebra} = {one})"
    if expr.op in ("true", "false"):
        return "T" if expr.op == "true" else "F"
    args = [tau_formula(arg, streams, algebra) for arg in expr.args]
    if expr.op == "!":
        return f"!({args[0]})"
    if expr.op == "^":
        return f"!({args[0]} <-> {args[1]})"
    return f"({args[0]} {expr.op} {args[1]})"
