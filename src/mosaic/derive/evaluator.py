"""Safe expression evaluator for derived variables.

The evaluator is intentionally minimal: it walks a parsed Python AST and
refuses anything that is not in a small whitelist. This is enough for the
expressions we publish in domain dictionaries (e.g. ``upwelling_mask``,
``hurricane_mpi``, ``sic_loss_rate``) without giving pipelines arbitrary
code-execution.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import xarray as xr

from mosaic._spec import DerivedVariable

# ---------------------------------------------------------------------------
# whitelist of allowed callables
# ---------------------------------------------------------------------------

_ALLOWED_FUNCS: dict[str, Any] = {
    "abs": np.abs,
    "exp": np.exp,
    "log": np.log,
    "log10": np.log10,
    "sqrt": np.sqrt,
    "where": xr.where,
    "minimum": np.minimum,
    "maximum": np.maximum,
    "clip": np.clip,
    "sin": np.sin,
    "cos": np.cos,
    "deg2rad": np.deg2rad,
    "rad2deg": np.rad2deg,
}

_ALLOWED_CONSTS: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "True": True,
    "False": False,
}

# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


class DerivationError(ValueError):
    """Raised when an expression references unknown names or unsupported syntax."""


@dataclass
class DerivationReport:
    """Diagnostics surfaced into the STAC mosaic:harmonization extension."""

    derived: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        total = len(self.derived) + len(self.failed)
        return 1.0 if total == 0 else len(self.derived) / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "derived": list(self.derived),
            "failed": dict(self.failed),
            "success_rate": self.success_rate,
        }


def apply_derived(
    ds: xr.Dataset,
    derived: list[DerivedVariable],
    *,
    strict: bool = True,
) -> tuple[xr.Dataset, DerivationReport]:
    """Compute and attach all declared derived variables.

    Variables are processed in declaration order; each result is added to the
    dataset before the next expression is evaluated, so later expressions can
    reference earlier ones.

    Parameters
    ----------
    ds
        The harmonized + QC'd dataset.
    derived
        List of :class:`DerivedVariable` from the validated pipeline spec.
    strict
        If True, raise :class:`DerivationError` on the first failure; otherwise
        record the failure in the :class:`DerivationReport` and continue.
    """
    report = DerivationReport()
    if not derived:
        return ds, report

    out = ds
    for spec in derived:
        if spec.expression is None:
            msg = f"derived variable '{spec.name}' has no expression"
            if strict:
                raise DerivationError(msg)
            report.failed[spec.name] = msg
            continue
        try:
            result = evaluate_expression(spec.expression, out)
        except DerivationError as exc:
            if strict:
                raise
            report.failed[spec.name] = str(exc)
            continue
        if not isinstance(result, xr.DataArray):
            # promote scalars / ndarray results to DataArray broadcast over time
            result = xr.DataArray(result)
        result.attrs.setdefault("long_name", spec.name)
        result.attrs.setdefault("mosaic:expression", spec.expression)
        result.attrs.setdefault("mosaic:derived", "true")
        out = out.assign({spec.name: result})
        report.derived.append(spec.name)

    return out, report


def evaluate_expression(expr: str, ds: xr.Dataset) -> Any:
    """Evaluate an expression against a dataset's data_vars.

    Names resolve in this order:
      1. ``ds.data_vars`` (returns an :class:`xarray.DataArray`)
      2. ``ds.coords`` (returns a coordinate :class:`xarray.DataArray`)
      3. constants whitelist (``pi``, ``e``, ``True``, ``False``)

    Function calls must be in :data:`_ALLOWED_FUNCS`; everything else raises
    :class:`DerivationError`.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise DerivationError(f"invalid expression syntax: {exc}") from exc
    return _eval_node(tree.body, ds)


# ---------------------------------------------------------------------------
# AST walker
# ---------------------------------------------------------------------------


_BIN_OPS: dict[type[ast.AST], Any] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
    ast.BitAnd: lambda a, b: a & b,
    ast.BitOr: lambda a, b: a | b,
    ast.BitXor: lambda a, b: a ^ b,
}

_UNARY_OPS: dict[type[ast.AST], Any] = {
    ast.USub: lambda a: -a,
    ast.UAdd: lambda a: +a,
    ast.Invert: lambda a: ~a,
    ast.Not: lambda a: np.logical_not(a),
}

_CMP_OPS: dict[type[ast.AST], Any] = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


def _eval_node(node: ast.AST, ds: xr.Dataset) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool, str)):
            return node.value
        raise DerivationError(f"unsupported constant type: {type(node.value)!r}")

    if isinstance(node, ast.Name):
        return _resolve_name(node.id, ds)

    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise DerivationError(f"unsupported binary operator: {type(node.op).__name__}")
        return op(_eval_node(node.left, ds), _eval_node(node.right, ds))

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise DerivationError(f"unsupported unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand, ds))

    if isinstance(node, ast.Compare):
        # Chained comparisons (a < b < c) are evaluated pairwise and AND-ed.
        left = _eval_node(node.left, ds)
        result: Any = None
        for op_node, comp in zip(node.ops, node.comparators, strict=True):
            op = _CMP_OPS.get(type(op_node))
            if op is None:
                raise DerivationError(f"unsupported comparison operator: {type(op_node).__name__}")
            right = _eval_node(comp, ds)
            piece = op(left, right)
            result = piece if result is None else (result & piece)
            left = right
        return result

    if isinstance(node, ast.BoolOp):
        # `and` / `or` collapse onto element-wise bitwise ops for arrays.
        operands = [_eval_node(o, ds) for o in node.values]
        if isinstance(node.op, ast.And):
            acc = operands[0]
            for x in operands[1:]:
                acc = acc & x
            return acc
        if isinstance(node.op, ast.Or):
            acc = operands[0]
            for x in operands[1:]:
                acc = acc | x
            return acc
        raise DerivationError(f"unsupported boolean operator: {type(node.op).__name__}")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise DerivationError("only direct function calls are allowed")
        fname = node.func.id
        if fname not in _ALLOWED_FUNCS:
            raise DerivationError(
                f"function '{fname}' is not in the allowed list: {sorted(_ALLOWED_FUNCS)}"
            )
        args = [_eval_node(a, ds) for a in node.args]
        if node.keywords:
            raise DerivationError(f"keyword arguments not supported (got '{fname}')")
        return _ALLOWED_FUNCS[fname](*args)

    raise DerivationError(f"unsupported expression node: {type(node).__name__}")


def _resolve_name(name: str, ds: xr.Dataset) -> Any:
    if name in ds.data_vars:
        return ds[name]
    if name in ds.coords:
        return ds[name]
    if name in _ALLOWED_CONSTS:
        return _ALLOWED_CONSTS[name]
    available = sorted(list(ds.data_vars) + list(ds.coords))
    raise DerivationError(
        f"unknown name '{name}' in expression; available data_vars/coords: {available}"
    )
