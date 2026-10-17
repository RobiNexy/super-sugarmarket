"""购物车整数行的神经树形求和。

@purpose 按设计文档 §5.3 把任意多行的整数和拆分为若干 10 行批次，每批调用一次神经加法器，
低 7 位作为下一轮的行，高位无损累加。
@spec [[tree-sum-neural-addition]]
@invariants 每行在 [0, 9_999_999]；每批至多 10 行（不足补零行）；高位累加器 H 与低位行的组合
满足 total = H·10^7 + low_final；空输入不调用模型。
@touches 被结账切片调用；模型通过 Predictor 协议注入，便于用精确 oracle 测试。
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from adder.onnx_runtime import rows_to_matrix

BATCH = 10
LOW_MOD = 10**7
MAX_ROW = 9_999_999


class Predictor(Protocol):
    def predict(
        self, matrix: np.ndarray[Any, np.dtype[np.int64]]
    ) -> tuple[np.ndarray[Any, np.dtype[np.int64]], np.ndarray[Any, np.dtype[np.int64]]]: ...


def validate_rows(rows: Any) -> np.ndarray[Any, np.dtype[np.int64]]:
    """校验一维整数行；返回 int64 数组。非法输入抛出 ValueError。"""
    arr = np.asarray(rows)
    if arr.ndim != 1:
        raise ValueError(f"rows must be one-dimensional, got shape {arr.shape}")
    if arr.size == 0:
        return arr.astype(np.int64)
    if arr.dtype.kind not in ("i", "u"):
        raise ValueError(f"rows must be integer typed, got {arr.dtype}")
    v = arr.astype(np.int64)
    if int(v.min()) < 0 or int(v.max()) > MAX_ROW:
        raise ValueError(f"row values must be in 0..{MAX_ROW}")
    return v


def _batch_sum(batch: np.ndarray[Any, np.dtype[np.int64]], model: Predictor) -> int:
    """对不超过 10 行的批次调用模型，返回神经和 S（整数）。不足 10 行补零。"""
    padded = np.zeros(BATCH, dtype=np.int64)
    padded[: batch.shape[0]] = batch
    matrix = rows_to_matrix(padded[None, :])
    digits, _ = model.predict(matrix)
    weights = 10 ** np.arange(digits.shape[1], dtype=np.int64)
    return int((digits[0].astype(np.int64) * weights).sum())


def tree_sum(rows: Any, model: Predictor) -> int:
    """返回神经树形求和结果。空输入返回 0。"""
    values = validate_rows(rows)
    if values.size == 0:
        return 0
    high_total = 0
    current = values
    while current.shape[0] > BATCH:
        next_rows: list[int] = []
        for start in range(0, current.shape[0], BATCH):
            s = _batch_sum(current[start : start + BATCH], model)
            next_rows.append(s % LOW_MOD)
            high_total += s // LOW_MOD
        current = np.asarray(next_rows, dtype=np.int64)
    s_final = _batch_sum(current, model)
    high_total += s_final // LOW_MOD
    return high_total * LOW_MOD + s_final % LOW_MOD
