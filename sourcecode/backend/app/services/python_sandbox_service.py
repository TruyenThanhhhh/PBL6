"""Python AST Sandbox an toàn tuyệt đối để tính toán công thức, thống kê bảng và kiểm tra điều kiện logic."""
import ast
import math
import operator
from typing import Any, Dict, List

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_SAFE_FUNCTIONS: Dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "pow": pow,
    "int": int,
    "float": float,
    "bool": bool,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
    "factorial": lambda n: math.factorial(min(int(n), 50)) if 0 <= int(n) <= 50 else _raise_val("factorial vượt quá 50"),
}

_SAFE_CONSTANTS: Dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "True": True,
    "False": False,
}

_MAX_STATEMENTS = 25
_MAX_EXPONENT = 1000
_MAX_FACTORS = 10 ** 12


def _raise_val(msg: str) -> Any:
    raise ValueError(msg)


def _eval_node(node: ast.AST, env: Dict[str, Any], depth: int = 0) -> Any:
    if depth > 40:
        raise ValueError("Biểu thức lồng nhau quá sâu.")

    if isinstance(node, ast.Expression):
        return _eval_node(node.body, env, depth + 1)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool, str)) or node.value is None:
            return node.value
        raise ValueError(f"Kiểu hằng số không được hỗ trợ: {type(node.value).__name__}")

    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[node.id]
        raise KeyError(f"Biến chưa được gán giá trị: '{node.id}'")

    if isinstance(node, ast.List):
        if len(node.elts) > 500:
            raise ValueError("Danh sách vượt quá 500 phần tử.")
        return [_eval_node(elt, env, depth + 1) for elt in node.elts]

    if isinstance(node, ast.Tuple):
        if len(node.elts) > 500:
            raise ValueError("Tuple vượt quá 500 phần tử.")
        return tuple(_eval_node(elt, env, depth + 1) for elt in node.elts)

    if isinstance(node, ast.Dict):
        if len(node.keys) > 200:
            raise ValueError("Dict vượt quá 200 khóa.")
        return {
            _eval_node(k, env, depth + 1): _eval_node(v, env, depth + 1)
            for k, v in zip(node.keys, node.values)
            if k is not None
        }

    if isinstance(node, ast.Subscript):
        target = _eval_node(node.value, env, depth + 1)
        idx = _eval_node(node.slice, env, depth + 1)
        return target[idx]

    if isinstance(node, ast.UnaryOp):
        op_fn = _UNARY_OPS.get(type(node.op))
        if not op_fn:
            raise ValueError(f"Toán tử một ngôi không được phép: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand, env, depth + 1))

    if isinstance(node, ast.BinOp):
        op_fn = _BIN_OPS.get(type(node.op))
        if not op_fn:
            raise ValueError(f"Toán tử hai ngôi không được phép: {type(node.op).__name__}")
        left = _eval_node(node.left, env, depth + 1)
        right = _eval_node(node.right, env, depth + 1)
        if isinstance(node.op, ast.Pow) and isinstance(right, (int, float)) and abs(right) > _MAX_EXPONENT:
            raise ValueError("Số mũ quá lớn.")
        if isinstance(node.op, ast.Mult) and isinstance(left, (list, tuple, str)) and isinstance(right, int) and right > 1000:
            raise ValueError("Phép nhân chuỗi/danh sách vượt giới hạn.")
        return op_fn(left, right)

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            val: Any = True
            for v in node.values:
                val = _eval_node(v, env, depth + 1)
                if not val:
                    return val
            return val
        if isinstance(node.op, ast.Or):
            val = False
            for v in node.values:
                val = _eval_node(v, env, depth + 1)
                if val:
                    return val
            return val
        raise ValueError("Toán tử logic không được hỗ trợ.")

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, env, depth + 1)
        for op, comparator in zip(node.ops, node.comparators):
            cmp_fn = _CMP_OPS.get(type(op))
            if not cmp_fn:
                raise ValueError(f"Phép so sánh không được phép: {type(op).__name__}")
            right = _eval_node(comparator, env, depth + 1)
            if not cmp_fn(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.IfExp):
        cond = _eval_node(node.test, env, depth + 1)
        return _eval_node(node.body if cond else node.orelse, env, depth + 1)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCTIONS:
            fn_name = getattr(node.func, "id", type(node.func).__name__)
            raise ValueError(f"Hàm không nằm trong danh sách cho phép: {fn_name}")
        if node.keywords:
            raise ValueError("Không hỗ trợ truyền keyword args trong sandbox.")
        args = [_eval_node(a, env, depth + 1) for a in node.args]
        result = _SAFE_FUNCTIONS[node.func.id](*args)
        if isinstance(result, (int, float)) and not isinstance(result, bool) and abs(result) > _MAX_FACTORS ** 4:
            raise ValueError("Giá trị tính toán vượt giới hạn an toàn.")
        return result

    raise ValueError(f"Cú pháp Python bị từ chối trong Sandbox: {type(node).__name__}")


def _format_value(val: Any) -> Any:
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise ValueError("Kết quả phép tính không xác định (NaN/Inf).")
        rounded = round(val, 6)
        return int(rounded) if rounded == int(rounded) and abs(rounded) < 1e12 else rounded
    return val


def evaluate_python_sandbox(
    variables: Optional[Dict[str, Any]],
    expressions: List[str],
) -> Dict[str, Any]:
    """
    Thực thi an toàn các biểu thức toán học / logic / thống kê bằng AST whitelist.
    Trả về dict: {'ok': bool, 'steps': [...], 'env': {...}, 'final_result': Any, 'error': str|None}.
    """
    if not expressions or not isinstance(expressions, list):
        return {"ok": False, "steps": [], "env": {}, "final_result": None, "error": "Không có biểu thức để thực thi."}

    if len(expressions) > _MAX_STATEMENTS:
        return {"ok": False, "steps": [], "env": {}, "final_result": None, "error": f"Vượt quá {_MAX_STATEMENTS} bước tính."}

    env: Dict[str, Any] = {}
    for k, v in (variables or {}).items():
        if isinstance(k, str) and k.isidentifier() and not k.startswith("_"):
            if isinstance(v, (int, float, bool, str, list, tuple)):
                env[k] = v

    steps: List[Dict[str, Any]] = []
    last_val: Any = None

    try:
        for raw_expr in expressions:
            code = (raw_expr or "").strip()
            if not code:
                continue
            tree = ast.parse(code, mode="exec")
            for stmt in tree.body:
                if isinstance(stmt, ast.Assign):
                    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                        raise ValueError("Chỉ hỗ trợ gán cho một tên biến đơn giản.")
                    var_name = stmt.targets[0].id
                    if var_name.startswith("_") or var_name in _SAFE_FUNCTIONS or var_name in _SAFE_CONSTANTS:
                        raise ValueError(f"Tên biến không hợp lệ: '{var_name}'")
                    val = _format_value(_eval_node(stmt.value, env))
                    env[var_name] = val
                    last_val = val
                    steps.append({"expr": code, "target": var_name, "value": val})
                elif isinstance(stmt, ast.Expr):
                    val = _format_value(_eval_node(stmt.value, env))
                    last_val = val
                    steps.append({"expr": code, "target": None, "value": val})
                else:
                    raise ValueError(f"Câu lệnh không được phép trong Sandbox: {type(stmt).__name__}")

        if not steps:
            return {"ok": False, "steps": [], "env": env, "final_result": None, "error": "Biểu thức rỗng."}

        return {
            "ok": True,
            "steps": steps,
            "env": env,
            "final_result": last_val,
            "error": None,
        }
    except ZeroDivisionError:
        return {"ok": False, "steps": steps, "env": env, "final_result": None, "error": "Lỗi chia cho 0."}
    except Exception as exc:
        return {"ok": False, "steps": steps, "env": env, "final_result": None, "error": str(exc)}
