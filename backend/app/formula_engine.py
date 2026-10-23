"""Small, safe Excel-style formula evaluator for the table module.

The evaluator intentionally supports a documented subset of Excel formulas.
It does not execute Python code and only exposes pure spreadsheet functions.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class FormulaError(ValueError):
    """Base class for formula-related errors."""


class UnsupportedFormulaError(FormulaError):
    def __init__(self, feature: str):
        self.feature = feature
        super().__init__(f"不支持的公式功能：{feature}")


class FormulaSyntaxError(FormulaError):
    pass


class FormulaEvaluationError(FormulaError):
    def __init__(self, value):
        self.display = value
        super().__init__(value)


@dataclass(frozen=True)
class FormulaToken:
    kind: str
    value: str


_TOKEN_RE = re.compile(
    r"""
    (?P<space>\s+)
    |(?P<string>"(?:[^"]|"")*")
    |(?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
    |(?P<cell>\$?[A-Za-z]{1,3}\$?\d+)
    |(?P<ident>[A-Za-z_][A-Za-z0-9_.]*)
    |(?P<op><=|>=|<>|[+\-*/^%&:(),=<>])
    |(?P<error>\#(?:NULL!|DIV/0!|VALUE!|REF!|NAME\?|NUM!|N/A))
    """,
    re.VERBOSE,
)


def tokenize(formula: str) -> list[FormulaToken]:
    if not isinstance(formula, str) or not formula.startswith("="):
        raise FormulaSyntaxError("公式必须以 = 开头")
    source = formula[1:]
    if "!" in source:
        raise UnsupportedFormulaError("跨工作表或外部引用")

    tokens = []
    position = 0
    while position < len(source):
        match = _TOKEN_RE.match(source, position)
        if not match:
            raise FormulaSyntaxError(f"无法识别公式内容：{source[position:position + 12]}")
        kind = match.lastgroup
        value = match.group()
        position = match.end()
        if kind != "space":
            tokens.append(FormulaToken(kind, value))
    tokens.append(FormulaToken("eof", ""))
    return tokens


class FormulaParser:
    """Recursive-descent parser producing a small tuple-based expression tree."""

    def __init__(self, formula: str):
        self.tokens = tokenize(formula)
        self.index = 0

    @property
    def current(self) -> FormulaToken:
        return self.tokens[self.index]

    def advance(self) -> FormulaToken:
        token = self.current
        self.index += 1
        return token

    def accept(self, kind: str, value: str | None = None) -> FormulaToken | None:
        token = self.current
        if token.kind != kind:
            return None
        if value is not None and token.value.upper() != value.upper():
            return None
        self.index += 1
        return token

    def expect(self, kind: str, value: str | None = None) -> FormulaToken:
        token = self.accept(kind, value)
        if token is None:
            expected = value or kind
            actual = self.current.value or "公式末尾"
            raise FormulaSyntaxError(f"公式缺少 {expected}，实际为 {actual}")
        return token

    def parse(self):
        if self.current.kind == "eof":
            raise FormulaSyntaxError("公式不能为空")
        node = self.parse_comparison()
        self.expect("eof")
        return node

    def parse_comparison(self):
        node = self.parse_concat()
        while self.current.kind == "op" and self.current.value in {
            "=",
            "<>",
            "<",
            ">",
            "<=",
            ">=",
        }:
            operator = self.advance().value
            node = ("binary", operator, node, self.parse_concat())
        return node

    def parse_concat(self):
        node = self.parse_additive()
        while self.accept("op", "&"):
            node = ("binary", "&", node, self.parse_additive())
        return node

    def parse_additive(self):
        node = self.parse_multiplicative()
        while self.current.kind == "op" and self.current.value in {"+", "-"}:
            operator = self.advance().value
            node = ("binary", operator, node, self.parse_multiplicative())
        return node

    def parse_multiplicative(self):
        node = self.parse_power()
        while self.current.kind == "op" and self.current.value in {"*", "/"}:
            operator = self.advance().value
            node = ("binary", operator, node, self.parse_power())
        return node

    def parse_power(self):
        node = self.parse_unary()
        if self.accept("op", "^"):
            node = ("binary", "^", node, self.parse_power())
        return node

    def parse_unary(self):
        if self.current.kind == "op" and self.current.value in {"+", "-"}:
            operator = self.advance().value
            return ("unary", operator, self.parse_unary())
        node = self.parse_primary()
        while self.accept("op", "%"):
            node = ("percent", node)
        return node

    def parse_primary(self):
        token = self.current
        if token.kind == "number":
            self.advance()
            return ("number", float(token.value))
        if token.kind == "string":
            self.advance()
            return ("string", token.value[1:-1].replace('""', '"'))
        if token.kind == "error":
            self.advance()
            return ("error", token.value)
        if token.kind == "cell":
            self.advance()
            start = _normalize_cell_reference(token.value)
            if self.accept("op", ":"):
                end_token = self.expect("cell")
                end = _normalize_cell_reference(end_token.value)
                return ("range", start, end)
            return ("cell", start)
        if token.kind == "ident":
            name = self.advance().value.upper()
            if name in {"TRUE", "FALSE"}:
                return ("boolean", name == "TRUE")
            if self.accept("op", "("):
                args = []
                if not self.accept("op", ")"):
                    while True:
                        args.append(self.parse_comparison())
                        if self.accept("op", ")"):
                            break
                        self.expect("op", ",")
                return ("call", name, args)
            raise FormulaSyntaxError(f"无法识别的名称：{name}")
        if self.accept("op", "("):
            node = self.parse_comparison()
            self.expect("op", ")")
            return node
        actual = token.value or "公式末尾"
        raise FormulaSyntaxError(f"公式语法错误，实际为 {actual}")


def _normalize_cell_reference(reference: str) -> str:
    return reference.replace("$", "").upper()


def _number(value) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if text.startswith("#"):
        raise FormulaEvaluationError(text)
    try:
        return float(text)
    except ValueError as exc:
        raise FormulaEvaluationError("#VALUE!") from exc


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    text = str(value).strip().upper()
    return text not in {"", "0", "FALSE", "NO"}


def _flatten(values) -> list:
    flattened = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(_flatten(value))
        else:
            flattened.append(value)
    return flattened


class FormulaEvaluator:
    def __init__(self, resolver):
        self.resolver = resolver
        self._memo = {}
        self._in_progress = set()

    def evaluate(self, formula: str):
        return self.evaluate_node(FormulaParser(formula).parse())

    def evaluate_node(self, node):
        kind = node[0]
        if kind == "number":
            return node[1]
        if kind == "string":
            return node[1]
        if kind == "boolean":
            return node[1]
        if kind == "error":
            raise FormulaEvaluationError(node[1])
        if kind == "cell":
            return self._cell(node[1])
        if kind == "range":
            return self._range(node[1], node[2])
        if kind == "unary":
            value = self.evaluate_node(node[2])
            return -_number(value) if node[1] == "-" else _number(value)
        if kind == "percent":
            return _number(self.evaluate_node(node[1])) / 100.0
        if kind == "binary":
            return self._binary(node[1], node[2], node[3])
        if kind == "call":
            return self._call(node[1], node[2])
        raise FormulaSyntaxError("未知公式表达式")

    def _cell(self, address: str):
        if address in self._memo:
            return self._memo[address]
        if address in self._in_progress:
            raise FormulaEvaluationError("#CIRC!")
        self._in_progress.add(address)
        try:
            value = self.resolver.cell(address)
            self._memo[address] = value
            return value
        finally:
            self._in_progress.discard(address)

    def _range(self, start: str, end: str):
        return self.resolver.range(start, end)

    def _binary(self, operator: str, left_node, right_node):
        left = self.evaluate_node(left_node)
        right = self.evaluate_node(right_node)
        if operator == "&":
            return _text(left) + _text(right)
        if operator == "=":
            return _compare(left, right) == 0
        if operator == "<>":
            return _compare(left, right) != 0
        if operator == "<":
            return _compare(left, right) < 0
        if operator == ">":
            return _compare(left, right) > 0
        if operator == "<=":
            return _compare(left, right) <= 0
        if operator == ">=":
            return _compare(left, right) >= 0

        left_number = _number(left)
        right_number = _number(right)
        if operator == "+":
            return left_number + right_number
        if operator == "-":
            return left_number - right_number
        if operator == "*":
            return left_number * right_number
        if operator == "/":
            if right_number == 0:
                raise FormulaEvaluationError("#DIV/0!")
            return left_number / right_number
        if operator == "^":
            try:
                return left_number**right_number
            except (OverflowError, ValueError, ZeroDivisionError) as exc:
                raise FormulaEvaluationError("#NUM!") from exc
        raise FormulaSyntaxError(f"不支持的运算符：{operator}")

    def _call(self, name: str, arg_nodes):
        normalized = name.removeprefix("_XLFN.")
        supported = {
            "SUM",
            "AVERAGE",
            "COUNT",
            "COUNTA",
            "MIN",
            "MAX",
            "IF",
            "ROUND",
            "ABS",
            "AND",
            "OR",
            "NOT",
            "CONCATENATE",
            "CONCAT",
        }
        if normalized not in supported:
            raise UnsupportedFormulaError(name)

        if normalized == "IF":
            if len(arg_nodes) not in {2, 3}:
                raise FormulaEvaluationError("#VALUE!")
            condition = self.evaluate_node(arg_nodes[0])
            if _truthy(condition):
                return self.evaluate_node(arg_nodes[1])
            return self.evaluate_node(arg_nodes[2]) if len(arg_nodes) == 3 else False

        if normalized in {"AND", "OR"}:
            values = []
            for arg_node in arg_nodes:
                value = self.evaluate_node(arg_node)
                if isinstance(value, list):
                    values.extend(_flatten(value))
                else:
                    values.append(value)
            result = [_truthy(value) for value in values]
            return all(result) if normalized == "AND" else any(result)

        values = []
        for arg_node in arg_nodes:
            value = self.evaluate_node(arg_node)
            if isinstance(value, list):
                values.extend(_flatten(value))
            else:
                values.append(value)

        if normalized == "SUM":
            return sum(_numeric_items(values))
        if normalized == "AVERAGE":
            items = _numeric_items(values)
            return sum(items) / len(items) if items else 0.0
        if normalized == "COUNT":
            return float(sum(1 for value in values if _is_number(value)))
        if normalized == "COUNTA":
            return float(sum(1 for value in values if value not in (None, "")))
        if normalized == "MIN":
            items = _numeric_items(values)
            return min(items) if items else 0.0
        if normalized == "MAX":
            items = _numeric_items(values)
            return max(items) if items else 0.0
        if normalized == "ROUND":
            if len(values) != 2:
                raise FormulaEvaluationError("#VALUE!")
            try:
                places = int(_number(values[1]))
                quantizer = Decimal("1").scaleb(-places)
                rounded = Decimal(str(_number(values[0]))).quantize(
                    quantizer, rounding=ROUND_HALF_UP
                )
                return float(rounded)
            except (InvalidOperation, ValueError) as exc:
                raise FormulaEvaluationError("#NUM!") from exc
        if normalized == "ABS":
            return abs(_number(values[0])) if values else 0.0
        if normalized == "NOT":
            return not _truthy(values[0]) if values else True
        if normalized in {"CONCATENATE", "CONCAT"}:
            return "".join(_text(value) for value in values)
        raise UnsupportedFormulaError(name)


def _numeric_items(values):
    return [
        _number(value)
        for value in values
        if value not in (None, "") and not isinstance(value, str)
        or _is_number(value)
    ]


def _is_number(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
        except ValueError:
            return False
        return True
    return False


def _compare(left, right) -> int:
    if _is_number(left) and _is_number(right):
        left_number = _number(left)
        right_number = _number(right)
        return (left_number > right_number) - (left_number < right_number)
    left_text = _text(left).casefold()
    right_text = _text(right).casefold()
    return (left_text > right_text) - (left_text < right_text)


def format_formula_result(value) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, FormulaEvaluationError):
        return value.display
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return "#NUM!"
        rounded = round(float(value), 12)
        if rounded.is_integer():
            return str(int(rounded))
        return f"{rounded:.12f}".rstrip("0").rstrip(".")
    return _text(value)
