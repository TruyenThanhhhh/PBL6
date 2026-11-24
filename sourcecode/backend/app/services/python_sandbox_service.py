"""Python AST Sandbox an toàn tuyệt đối để tính toán công thức, thống kê bảng và kiểm tra điều kiện logic."""
import ast
import math
import operator
import re
from typing import Any, Dict, List, Optional

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

def _safe_pow(base: Any, exp: Any, mod: Any = None) -> Any:
    if isinstance(exp, (int, float)) and abs(exp) > _MAX_EXPONENT:
        raise ValueError("Số mũ quá lớn.")
    res = pow(base, exp) if mod is None else pow(base, exp, mod)
    if isinstance(res, (int, float)) and not isinstance(res, bool) and abs(res) > _MAX_FACTORS ** 4:
        raise ValueError("Giá trị lũy thừa vượt giới hạn an toàn.")
    return res


def _safe_solve_quadratic(a: float, b: float, c: float) -> List[float]:
    if abs(float(a)) < 1e-12:
        return [round(-float(c) / float(b), 6)] if abs(float(b)) >= 1e-12 else []
    delta = float(b) ** 2 - 4.0 * float(a) * float(c)
    if delta < -1e-12:
        return []
    if abs(delta) <= 1e-12:
        return [round(-float(b) / (2.0 * float(a)), 6)]
    sq = math.sqrt(delta)
    r1 = round((-float(b) - sq) / (2.0 * float(a)), 6)
    r2 = round((-float(b) + sq) / (2.0 * float(a)), 6)
    return sorted([r1, r2])


def _safe_solve_linear_2x2(a1: float, b1: float, c1: float, a2: float, b2: float, c2: float) -> List[float]:
    det = float(a1) * float(b2) - float(a2) * float(b1)
    if abs(det) < 1e-12:
        return []
    x = round((float(c1) * float(b2) - float(c2) * float(b1)) / det, 6)
    y = round((float(a1) * float(c2) - float(a2) * float(c1)) / det, 6)
    return [x, y]


def _safe_solve_eq(expr_str: str, var_name: str = "x") -> List[float]:
    """Giải phương trình đại số 1 ẩn an toàn bằng SymPy (chỉ cho phép ký tự toán học chuẩn)."""
    raw = str(expr_str or "").strip()
    vname = str(var_name or "x").strip()
    if not raw or len(raw) > 120 or not re.fullmatch(r"[A-Za-z]", vname):
        raise ValueError("Biểu thức phương trình không hợp lệ.")
    norm = _normalize_math_expression(raw).replace("^", "**")
    if not re.fullmatch(r"[0-9A-Za-z\s\+\-\*\/\(\)\.=]+", norm):
        raise ValueError("Phương trình chứa ký tự không được phép.")
    norm = re.sub(rf"(\d)\s*({re.escape(vname)})\b", r"\1*\2", norm)
    import sympy as sp
    sym = sp.Symbol(vname, real=True)
    if "=" in norm:
        lhs_s, rhs_s = norm.split("=", 1)
        eq = sp.sympify(lhs_s, locals={vname: sym}) - sp.sympify(rhs_s, locals={vname: sym})
    else:
        eq = sp.sympify(norm, locals={vname: sym})
    sols = sp.solve(eq, sym)
    out: List[float] = []
    for s in sols[:8]:
        try:
            fval = float(s.evalf())
            if not math.isnan(fval) and not math.isinf(fval):
                out.append(int(round(fval)) if abs(fval - round(fval)) < 1e-9 else round(fval, 6))
        except Exception:
            continue
    return sorted(set(out))


_SAFE_FUNCTIONS: Dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "pow": _safe_pow,
    "solve_quadratic": _safe_solve_quadratic,
    "solve_linear_2x2": _safe_solve_linear_2x2,
    "solve_eq": _safe_solve_eq,
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
        if isinstance(node.op, ast.Mult):
            if (isinstance(left, (list, tuple, str)) and isinstance(right, int) and right > 1000) or (
                isinstance(right, (list, tuple, str)) and isinstance(left, int) and left > 1000
            ):
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


def _normalize_math_expression(expr: str) -> str:
    """Chuẩn hóa ký hiệu toán học Unicode thường gặp của LLM (π, ×, ÷, ², ³, √) sang cú pháp Python hợp lệ."""
    s = (expr or "").strip()
    if not s:
        return ""
    s = s.replace("π", "pi").replace("×", "*").replace("÷", "/").replace("−", "-")
    s = re.sub(r"\bmath\.(pi|e|sqrt|sin|cos|tan|log|log10|log2|exp|ceil|floor|factorial)\b", r"\1", s)
    s = s.replace("²", "**2").replace("³", "**3").replace("⁴", "**4")
    s = re.sub(r"√\s*\(", "sqrt(", s)
    s = re.sub(r"√\s*(\d+(?:\.\d+)?|[A-Za-z_]\w*)", r"sqrt(\1)", s)
    # Chèn dấu nhân ẩn kiểu 2pi -> 2*pi hoặc 3(a+b) không phá hàm
    s = re.sub(r"(\d)\s*(pi)\b", r"\1*\2", s)
    return s


def _format_value(val: Any) -> Any:
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise ValueError("Kết quả phép tính không xác định (NaN/Inf).")
        if val != 0 and abs(val) < 1e-4:
            return val
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
            code = _normalize_math_expression(raw_expr)
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
                    raw_val = _eval_node(stmt.value, env)
                    if isinstance(raw_val, float) and (math.isnan(raw_val) or math.isinf(raw_val)):
                        raise ValueError("Kết quả phép tính không xác định (NaN/Inf).")
                    env[var_name] = raw_val
                    disp_val = _format_value(raw_val)
                    last_val = disp_val
                    steps.append({"expr": code, "target": var_name, "value": disp_val})
                elif isinstance(stmt, ast.Expr):
                    raw_val = _eval_node(stmt.value, env)
                    disp_val = _format_value(raw_val)
                    last_val = disp_val
                    steps.append({"expr": code, "target": None, "value": disp_val})
                else:
                    raise ValueError(f"Câu lệnh không được phép trong Sandbox: {type(stmt).__name__}")

        if not steps:
            return {"ok": False, "steps": [], "env": env, "final_result": None, "error": "Biểu thức rỗng."}

        formatted_env = {k: _format_value(v) for k, v in env.items()}
        return {
            "ok": True,
            "steps": steps,
            "env": formatted_env,
            "final_result": last_val,
            "error": None,
        }
    except ZeroDivisionError:
        return {"ok": False, "steps": steps, "env": env, "final_result": None, "error": "Lỗi chia cho 0."}
    except Exception as exc:
        return {"ok": False, "steps": steps, "env": env, "final_result": None, "error": str(exc)}
