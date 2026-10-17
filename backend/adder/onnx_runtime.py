"""基于 ONNX Runtime 的竖式加法 CPU 推理封装（不依赖 PyTorch）。

@purpose 提供会话复用的小批量推理接口，并在进入 ORT 前校验输入。
@spec [[adder-onnx-cpu-inference]]
@invariants 输入须为整数类型、形状 [B, 10, 8]、B ≥ 1、取值 0..9、最高列全为 0；否则抛出 ValueError。
@adr [[ADR-0005-onnx-runtime-cpu-deployment]]
@touches 被后续结账切片的 tree_sum 调用；运行时仅依赖 numpy 与 onnxruntime。
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, cast

import numpy as np

from adder.data import COLS, MAX_ROW_VALUE, ROWS

# TODO(types): onnxruntime 未提供类型存根，集中在此处以 Any 隔离
ort: Any = importlib.import_module("onnxruntime")
INPUT_NAME = "matrix"


def validate_matrix(matrix: Any) -> np.ndarray[Any, np.dtype[np.int64]]:
    """校验并返回 int64 连续数组；非法输入抛出 ValueError。"""
    if not isinstance(matrix, np.ndarray):
        raise ValueError("matrix must be a numpy.ndarray")
    arr_in = cast(np.ndarray[Any, np.dtype[Any]], matrix)
    if arr_in.dtype.kind not in ("i", "u"):
        raise ValueError(f"matrix must be integer typed, got {arr_in.dtype}")
    if arr_in.ndim != 3 or arr_in.shape[1:] != (ROWS, COLS):
        raise ValueError(f"matrix must have shape [B, {ROWS}, {COLS}], got {arr_in.shape}")
    if arr_in.shape[0] < 1:
        raise ValueError("batch must be >= 1")
    arr = arr_in.astype(np.int64, copy=False)
    if int(arr.min()) < 0 or int(arr.max()) > 9:
        raise ValueError("digits must be in 0..9")
    if bool(np.any(arr[:, :, COLS - 1] != 0)):
        raise ValueError("most significant column must be all zero")
    return np.ascontiguousarray(arr)


def rows_to_matrix(values: np.ndarray[Any, np.dtype[Any]]) -> np.ndarray[Any, np.dtype[np.int64]]:
    """把 [B, 10] 的整数行（每行 0..9,999,999）转换为 [B, 10, 8] 数字矩阵（最低位在前）。"""
    vals = np.asarray(values)
    if vals.ndim != 2 or vals.shape[1] != ROWS:
        raise ValueError(f"values must have shape [B, {ROWS}]")
    if vals.dtype.kind not in ("i", "u"):
        raise ValueError("values must be integer typed")
    v = vals.astype(np.int64, copy=False)
    if int(v.min()) < 0 or int(v.max()) > MAX_ROW_VALUE:
        raise ValueError("row values must be in 0..9999999")
    powers = 10 ** np.arange(COLS, dtype=np.int64)
    return ((v[:, :, None] // powers) % 10).astype(np.int64)


class OnnxAdder:
    """ONNX Runtime 推理会话（创建一次，多次复用）。"""

    def __init__(self, path: Path, threads: int = 1) -> None:
        if threads < 1:
            raise ValueError("threads must be >= 1")
        if not path.exists():
            raise FileNotFoundError(f"ONNX model not found: {path}")
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self._session = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
        self.threads = threads

    @property
    def session(self) -> Any:
        """底层 ORT 会话，仅供基准与调试使用；业务代码应调用 predict/logits。"""
        return self._session

    def logits(
        self, matrix: np.ndarray[Any, np.dtype[Any]]
    ) -> tuple[np.ndarray[Any, np.dtype[np.float32]], np.ndarray[Any, np.dtype[np.float32]]]:
        arr = validate_matrix(matrix)
        outputs = cast(
            list[np.ndarray[Any, np.dtype[np.float32]]], self._session.run(None, {INPUT_NAME: arr})
        )
        return outputs[0], outputs[1]

    def predict(
        self, matrix: np.ndarray[Any, np.dtype[Any]]
    ) -> tuple[np.ndarray[Any, np.dtype[np.int64]], np.ndarray[Any, np.dtype[np.int64]]]:
        """返回 (数字 [B,8], 进位 [B,8])，均为 argmax 结果。"""
        digit_logits, carry_logits = self.logits(matrix)
        return digit_logits.argmax(axis=-1), carry_logits.argmax(axis=-1)
