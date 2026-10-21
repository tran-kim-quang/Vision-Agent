"""Restricted mathematical expressions accepted by the GeoGebra compiler."""

from __future__ import annotations

import ast
import io
import math
import tokenize
from dataclasses import dataclass


ALLOWED_FUNCTIONS = frozenset({"sin", "cos", "tan", "exp", "log", "sqrt", "abs"})
ALLOWED_CONSTANTS = frozenset({"pi", "e"})
MAX_EXPRESSION_LENGTH = 500
MAX_EXPRESSION_DEPTH = 32


class ExpressionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ExpressionNode:
    kind: str
    value: str | float | int | None = None
    children: tuple["ExpressionNode", ...] = ()


def _normalize_caret(text: str) -> str:
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError) as exc:
        raise ExpressionError("invalid_expression", str(exc)) from exc
    return tokenize.untokenize(
        (token.type, "**" if token.type == tokenize.OP and token.string == "^" else token.string)
        for token in tokens
    )


def parse_expression(text: str, variables: frozenset[str]) -> ExpressionNode:
    if not isinstance(text, str) or not text.strip():
        raise ExpressionError("invalid_expression", "expression must be non-empty text")
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError("expression_too_long", f"expression exceeds {MAX_EXPRESSION_LENGTH} characters")
    try:
        parsed = ast.parse(_normalize_caret(text), mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise ExpressionError("invalid_expression", "expression syntax is invalid") from exc

    binary = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "^"}
    unary = {ast.UAdd: "+", ast.USub: "-"}

    def convert(node: ast.AST, depth: int) -> ExpressionNode:
        if depth > MAX_EXPRESSION_DEPTH:
            raise ExpressionError("expression_too_deep", f"expression exceeds depth {MAX_EXPRESSION_DEPTH}")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            try:
                finite = math.isfinite(float(node.value))
            except OverflowError:
                finite = False
            if not finite:
                raise ExpressionError("invalid_expression", "numbers must be finite")
            return ExpressionNode("number", node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables and node.id not in ALLOWED_CONSTANTS:
                raise ExpressionError("unknown_name", f"name {node.id!r} is not allowed")
            return ExpressionNode("name", node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            return ExpressionNode("binary", binary[type(node.op)], (convert(node.left, depth + 1), convert(node.right, depth + 1)))
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary:
            return ExpressionNode("unary", unary[type(node.op)], (convert(node.operand, depth + 1),))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ALLOWED_FUNCTIONS and len(node.args) == 1 and not node.keywords:
            return ExpressionNode("call", node.func.id, (convert(node.args[0], depth + 1),))
        raise ExpressionError("invalid_expression", f"unsupported expression element: {type(node).__name__}")

    return convert(parsed.body, 1)


def emit_expression(node: ExpressionNode, rename: dict[str, str] | None = None) -> str:
    rename = rename or {}
    if node.kind == "number":
        return repr(node.value)
    if node.kind == "name":
        return rename.get(str(node.value), str(node.value))
    if node.kind == "binary":
        return f"({emit_expression(node.children[0], rename)} {node.value} {emit_expression(node.children[1], rename)})"
    if node.kind == "unary":
        return f"({node.value}{emit_expression(node.children[0], rename)})"
    if node.kind == "call":
        return f"{node.value}({emit_expression(node.children[0], rename)})"
    raise ExpressionError("invalid_expression", f"unknown node kind {node.kind!r}")
