"""ONNX 导出与 ONNX Runtime 推理封装的测试。

@purpose 验证导出文件通过 onnx.checker、batch 维动态、ORT 与 PyTorch 数值一致、
输入校验严格，以及训练检查点上的精度门槛。
@spec [[adder-onnx-cpu-inference]]
@covers adder/onnx_export.py（export_onnx、check_onnx_file、verify_against_torch）、
adder/onnx_runtime.py（validate_matrix、rows_to_matrix、OnnxAdder）
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from adder.data import (
    fixed_boundary_values,
    make_generator,
    sample_values,
    seed_everything,
    targets,
    to_matrix,
)
from adder.infer import from_trained
from adder.model import AdderTransformer, ModelConfig, load_checkpoint
from adder.onnx_export import check_onnx_file, export_onnx
from adder.onnx_runtime import OnnxAdder, rows_to_matrix, validate_matrix

SMALL = ModelConfig(d_model=32, n_layers=2, n_heads=2, d_ff=64, dropout=0.0)
CKPT = Path("checkpoints/adder/adder-final.pt")


@pytest.fixture(scope="module")
def small_onnx(tmp_path_factory: pytest.TempPathFactory) -> tuple[AdderTransformer, Path]:
    seed_everything(0)
    trained = AdderTransformer(SMALL).eval()
    path = tmp_path_factory.mktemp("onnx") / "adder.onnx"
    export_onnx(from_trained(trained), path)
    return trained, path


def _tensor(arr: np.ndarray) -> torch.Tensor:
    # TODO(types): torch.from_numpy 存根返回 partially unknown，上游问题
    return torch.from_numpy(arr)  # pyright: ignore[reportUnknownMemberType]


def _mats(batch: int, seed: int) -> np.ndarray:
    return to_matrix(sample_values(batch, make_generator(seed), boundary_frac=0.1)).numpy()


def test_exported_model_passes_onnx_checker(small_onnx: tuple[AdderTransformer, Path]) -> None:
    _, path = small_onnx
    assert path.exists()
    check_onnx_file(path)


def test_batch_dimension_is_dynamic(small_onnx: tuple[AdderTransformer, Path]) -> None:
    _, path = small_onnx
    adder = OnnxAdder(path)
    for b in (1, 2, 7, 33):
        d, c = adder.predict(_mats(b, seed=b))
        assert d.shape == (b, 8)
        assert c.shape == (b, 8)


def test_onnx_matches_torch_graph_numerically(small_onnx: tuple[AdderTransformer, Path]) -> None:
    trained, path = small_onnx
    adder = OnnxAdder(path)
    mats = _mats(256, seed=5)
    with torch.inference_mode():
        out = trained(_tensor(mats))
    d_o, c_o = adder.logits(mats)
    assert np.allclose(d_o, out["digit_logits"].numpy(), atol=1e-4)
    assert np.allclose(c_o, out["carry_logits"].numpy(), atol=1e-4)


def test_validate_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError):
        validate_matrix(np.zeros((2, 9, 8), dtype=np.int64))


def test_validate_rejects_empty_batch() -> None:
    with pytest.raises(ValueError):
        validate_matrix(np.zeros((0, 10, 8), dtype=np.int64))


def test_validate_rejects_float_dtype() -> None:
    with pytest.raises(ValueError):
        validate_matrix(np.zeros((1, 10, 8), dtype=np.float32))


def test_validate_rejects_digit_out_of_range() -> None:
    m = np.zeros((1, 10, 8), dtype=np.int64)
    m[0, 0, 0] = 10
    with pytest.raises(ValueError):
        validate_matrix(m)


def test_validate_rejects_nonzero_most_significant_column() -> None:
    m = np.zeros((1, 10, 8), dtype=np.int64)
    m[0, 3, 7] = 1
    with pytest.raises(ValueError):
        validate_matrix(m)


def test_rows_to_matrix_matches_training_encoding() -> None:
    values = sample_values(64, make_generator(9), boundary_frac=0.2).numpy()
    expected = to_matrix(_tensor(values)).numpy()
    assert np.array_equal(rows_to_matrix(values), expected)


def test_rows_to_matrix_rejects_out_of_range_rows() -> None:
    with pytest.raises(ValueError):
        rows_to_matrix(np.full((1, 10), 10_000_000, dtype=np.int64))


def test_missing_model_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        OnnxAdder(tmp_path / "missing.onnx")


def test_threads_must_be_positive(small_onnx: tuple[AdderTransformer, Path]) -> None:
    _, path = small_onnx
    with pytest.raises(ValueError):
        OnnxAdder(path, threads=0)


@pytest.mark.skipif(not CKPT.exists(), reason="需要已训练的 fp32 检查点（backend/checkpoints）")
def test_trained_model_meets_accuracy_gate_via_onnx(tmp_path: Path) -> None:
    trained = load_checkpoint(CKPT, device="cpu")
    path = tmp_path / "adder.onnx"
    export_onnx(from_trained(trained), path)
    adder = OnnxAdder(path)
    values = sample_values(10_000, make_generator(12_345), boundary_frac=0.0)
    mat = to_matrix(values).numpy()
    d_true, _ = targets(_tensor(mat))
    d_pred, _ = adder.predict(mat)
    assert float((d_pred == d_true.numpy()).all(axis=-1).mean()) >= 0.999
    bnd = to_matrix(fixed_boundary_values()).numpy()
    d_b, _ = targets(_tensor(bnd))
    pb, _ = adder.predict(bnd)
    assert bool((pb == d_b.numpy()).all())
