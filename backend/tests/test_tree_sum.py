"""神经树形求和 tree_sum 的测试。

@purpose 用精确 oracle 验证树形归并的代数正确性、批次数、边界与输入校验；
用训练好的 ONNX 模型做小样本冒烟测试。
@spec [[tree-sum-neural-addition]]
@covers adder/tree_sum.py（tree_sum、validate_rows）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from adder.onnx_runtime import OnnxAdder
from adder.tree_sum import MAX_ROW, tree_sum


class ExactOracle:
    """精确加法替身：对矩阵内各行求精确和，返回其 8 位数字，并记录调用次数与批次形状。"""

    def __init__(self) -> None:
        self.calls = 0
        self.shapes: list[tuple[int, ...]] = []

    def predict(
        self, matrix: np.ndarray[Any, np.dtype[np.int64]]
    ) -> tuple[np.ndarray[Any, np.dtype[np.int64]], np.ndarray[Any, np.dtype[np.int64]]]:
        self.calls += 1
        self.shapes.append(tuple(matrix.shape))
        weights = 10 ** np.arange(8, dtype=np.int64)
        digits = np.zeros((matrix.shape[0], 8), dtype=np.int64)
        for b in range(matrix.shape[0]):
            v = int((matrix[b].sum(axis=0) * weights).sum())
            for i in range(8):
                digits[b, i] = (v // 10**i) % 10
        return digits, np.zeros_like(digits)


def _rows(n: int, seed: int) -> list[int]:
    rng = np.random.default_rng(seed)
    return [int(x) for x in rng.integers(0, MAX_ROW + 1, size=n)]


@pytest.mark.parametrize("n", [1, 2, 9, 10, 11, 37, 100, 101, 300])
def test_exact_oracle_matches_integer_sum(n: int) -> None:
    rows = _rows(n, seed=n)
    assert tree_sum(rows, ExactOracle()) == sum(rows)


def test_empty_input_returns_zero_without_calling_model() -> None:
    oracle = ExactOracle()
    assert tree_sum([], oracle) == 0
    assert oracle.calls == 0


def test_ten_rows_use_one_call() -> None:
    oracle = ExactOracle()
    tree_sum(_rows(10, seed=1), oracle)
    assert oracle.calls == 1


def test_eleven_rows_use_three_calls() -> None:
    # 11 行 -> 2 批（10 行 + 1 行补零）-> 最终 1 批
    oracle = ExactOracle()
    rows = _rows(11, seed=2)
    assert tree_sum(rows, oracle) == sum(rows)
    assert oracle.calls == 3


def test_hundred_rows_use_eleven_calls() -> None:
    # 100 行 -> 10 批 -> 最终 1 批
    oracle = ExactOracle()
    rows = _rows(100, seed=3)
    assert tree_sum(rows, oracle) == sum(rows)
    assert oracle.calls == 11


def test_every_batch_is_padded_to_ten_rows() -> None:
    oracle = ExactOracle()
    tree_sum(_rows(23, seed=4), oracle)
    assert all(shape == (1, 10, 8) for shape in oracle.shapes)


def test_ten_maximum_rows_sum_to_99999990() -> None:
    oracle = ExactOracle()
    assert tree_sum([MAX_ROW] * 10, oracle) == 99_999_990


def test_many_maximum_rows_stay_exact() -> None:
    rows = [MAX_ROW] * 257
    assert tree_sum(rows, ExactOracle()) == MAX_ROW * 257


@pytest.mark.parametrize(
    "bad",
    [
        [-1],
        [MAX_ROW + 1],
        [1.5, 2.0],
        [[1, 2], [3, 4]],
    ],
)
def test_invalid_rows_are_rejected_without_calling_model(bad: Any) -> None:
    oracle = ExactOracle()
    with pytest.raises(ValueError):
        tree_sum(bad, oracle)
    assert oracle.calls == 0


CKPT_ONNX = Path("checkpoints/adder-onnx/adder.onnx")


@pytest.mark.skipif(
    not CKPT_ONNX.exists(), reason="需要已导出的 ONNX 模型（checkpoints/adder-onnx）"
)
def test_real_onnx_model_returns_reproducible_integer_for_small_carts() -> None:
    adder = OnnxAdder(CKPT_ONNX)
    rows = [1999, 250, 4_000_000, 7, 9_999_999, 42, 0, 123456, 88, 5, 6, 7]
    first = tree_sum(rows, adder)
    second = tree_sum(rows, adder)
    assert isinstance(first, int)
    assert first == second
    assert first >= 0
