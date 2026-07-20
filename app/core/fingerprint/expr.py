"""指纹规则表达式 DSL，移植自原 app/services/expr.py。

原实现基于 pyparsing；此处用纯 Python 递归下降解析器重写，无第三方依赖。

语法：
    expression := or_expr
    or_expr    := and_expr ( "||" and_expr )*
    and_expr   := not_expr ( "&&" not_expr )*
    not_expr   := "!" not_expr | primary
    primary    := "(" expression ")" | atom
    atom       := variable op value | variable
    op         := "==" | "!=" | "="
    value      := quoted_string | integer
    variable   := [A-Za-z_][A-Za-z0-9_]*

变量取值由调用方通过 variables 字典提供（body/header/title/icon_hash）。
"""
from __future__ import annotations

from typing import Any, Callable


class ExprError(ValueError):
    pass


def _unquote_string(s: str) -> str:
    """去掉双引号并处理转义。"""
    s = s[1:-1]
    return (s.replace('\\\\', '\x00')
             .replace('\\n', '\n')
             .replace('\\t', '\t')
             .replace('\\r', '\r')
             .replace('\\"', '"')
             .replace('\x00', '\\'))


class _Parser:
    """递归下降解析器，产出由 (op, left, right) 组成的嵌套元组 AST。"""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.n = len(text)

    def _skip_ws(self):
        while self.pos < self.n and self.text[self.pos] in ' \t\r\n':
            self.pos += 1

    def _peek(self) -> str:
        return self.text[self.pos] if self.pos < self.n else ''

    def _match(self, s: str) -> bool:
        self._skip_ws()
        if self.text.startswith(s, self.pos):
            self.pos += len(s)
            return True
        return False

    def parse(self):
        node = self._or_expr()
        self._skip_ws()
        if self.pos != self.n:
            raise ExprError(f"unexpected token at pos {self.pos}: {self.text[self.pos:]!r}")
        return node

    def _or_expr(self):
        left = self._and_expr()
        while self._match('||'):
            right = self._and_expr()
            left = ('||', left, right)
        return left

    def _and_expr(self):
        left = self._not_expr()
        while self._match('&&'):
            right = self._not_expr()
            left = ('&&', left, right)
        return left

    def _not_expr(self):
        if self._match('!'):
            operand = self._not_expr()
            return ('!', operand, None)
        return self._primary()

    def _primary(self):
        self._skip_ws()
        if self._match('('):
            node = self._or_expr()
            if not self._match(')'):
                raise ExprError("missing closing ')'")
            return node
        return self._atom()

    def _atom(self):
        var = self._variable()
        self._skip_ws()
        for op in ('==', '!=', '='):
            if self._match(op):
                val = self._value()
                return (op, var, val)
        # 裸变量（布尔判断）
        return ('=', var, True)

    def _variable(self) -> str:
        self._skip_ws()
        start = self.pos
        while self.pos < self.n and (self.text[self.pos].isalnum() or self.text[self.pos] == '_'):
            self.pos += 1
        if self.pos == start:
            raise ExprError(f"expected variable at pos {start}")
        return self.text[start:self.pos]

    def _value(self) -> Any:
        self._skip_ws()
        if self._peek() == '"':
            start = self.pos
            self.pos += 1  # 跳过开头引号
            while self.pos < self.n:
                c = self.text[self.pos]
                if c == '\\' and self.pos + 1 < self.n:
                    self.pos += 2
                    continue
                if c == '"':
                    self.pos += 1
                    return _unquote_string(self.text[start:self.pos])
                self.pos += 1
            raise ExprError("unterminated string literal")
        # 整数
        start = self.pos
        while self.pos < self.n and self.text[self.pos].isdigit():
            self.pos += 1
        if self.pos == start:
            raise ExprError(f"expected value at pos {start}")
        return int(self.text[start:self.pos])


# 操作符实现
# 注意：与原 expr.py 一致，运算方向是 evaluate(parsed[2]) op evaluate(parsed[0])
# 即 value op variable：例如 body="abc" 解析为 ('=', 'body', 'abc')，
# 求值时 _OPS['='](value='abc', variable=body字符串) → 'abc' in body
def _op_eq(value: Any, variable: Any) -> bool:
    """=  表示包含（value in variable）。非字符串变量退化为相等比较。"""
    if isinstance(variable, str):
        return value in variable
    if isinstance(variable, (list, tuple, set)):
        return value in variable
    return value == variable


def _op_str_eq(value: Any, variable: Any) -> bool:
    """== 表示完全相等。"""
    return value == variable


def _op_ne(value: Any, variable: Any) -> bool:
    """!= 表示不包含。"""
    if isinstance(variable, str):
        return value not in variable
    if isinstance(variable, (list, tuple, set)):
        return value not in variable
    return value != variable


_OPS: dict[str, Callable] = {
    '=': _op_eq,
    '==': _op_str_eq,
    '!=': _op_ne,
    '!': lambda x, _y: not x,
    '&&': lambda x, y: bool(x) and bool(y),
    '||': lambda x, y: bool(x) or bool(y),
}


def parse_expression(expression: str):
    """解析表达式为 AST（嵌套元组）。"""
    return _Parser(expression).parse()


def evaluate_expression(parsed, variables: dict) -> bool:
    """递归求值。"""
    if isinstance(parsed, str):
        if parsed in variables:
            return variables[parsed]
        raise ExprError(f"Unknown variable: {parsed}")

    if not isinstance(parsed, tuple):
        raise ExprError(f"invalid AST node: {parsed!r}")

    op = parsed[0]
    if op == '!':
        return _OPS[op](evaluate_expression(parsed[1], variables), None)
    # AST: (op, var_node, value_node)  —— 与原 expr.py 顺序一致 op(value, variable)
    variable = evaluate_expression(parsed[1], variables)
    value_node = parsed[2]
    if isinstance(value_node, tuple):
        value = evaluate_expression(value_node, variables)
    else:
        value = value_node
    return _OPS[op](value, variable)


def evaluate(expression: str, variables: dict) -> bool:
    return evaluate_expression(parse_expression(expression), variables)


def _check_expression(expression: str) -> None:
    variables = {'body': "", 'header': "", 'title': "", 'icon_hash': ""}
    evaluate(expression, variables)


def check_expression(expression: str) -> bool:
    try:
        _check_expression(expression)
        return True
    except Exception as e:
        from ...logger import get_logger
        get_logger().error(f"Invalid expression: {expression}  exception: {e}")
        return False


def check_expression_with_error(expression: str) -> tuple[bool, Exception | None]:
    try:
        _check_expression(expression)
        return True, None
    except Exception as e:
        return False, e
