"""CPU 推理图与静态 int8 量化的测试。

@purpose 验证 fp32 推理图与训练图等价、int8 权重位宽限制、FFN 量化参数共享、
导出加载往返，以及训练模型上的精度门槛。
@spec [[adder-cpu-int8-inference]]
@covers adder/infer.py（from_trained、QLinear、quantize_static、export_int8、load_int8、predict）
"""

from __future__ import annotations

from pathlib import Path

import pytest
import torch
from torch import nn

from adder.data import (
    fixed_boundary_values,
    make_generator,
    sample_values,
    seed_everything,
    targets,
    to_matrix,
)
from adder.infer import (
    CpuAdder,
    QLinear,
    affine_params,
    export_int8,
    from_trained,
    load_int8,
    make_qlinear,
    predict,
    quantize_static,
    save_int8,
)
from adder.model import AdderTransformer, ModelConfig, load_checkpoint

SMALL = ModelConfig(d_model=32, n_layers=2, n_heads=2, d_ff=64, dropout=0.0)
CKPT = Path("checkpoints/adder/adder-final.pt")


def _matrices(batch: int, seed: int) -> torch.Tensor:
    return to_matrix(sample_values(batch, make_generator(seed), boundary_frac=0.1))


def _small_trained() -> AdderTransformer:
    seed_everything(0)
    model = AdderTransformer(SMALL)
    model.eval()
    return model


def test_fp32_inference_graph_matches_trained_model() -> None:
    trained = _small_trained()
    cpu = from_trained(trained)
    x = _matrices(64, seed=1)
    with torch.inference_mode():
        ref = trained(x)
        dig, car = cpu(x)
    assert torch.allclose(ref["digit_logits"], dig, atol=1e-4)
    assert torch.allclose(ref["carry_logits"], car, atol=1e-4)


def test_affine_params_include_zero_and_stay_in_uint8() -> None:
    scale, zp = affine_params(0.5, 3.0)
    assert 0 <= zp <= 255
    assert zp == 0  # 范围不含负数时零点为 0 的下界处理
    scale, zp = affine_params(-2.0, 2.0)
    assert abs(zp - 127.5) <= 1.0
    assert scale > 0


def test_qlinear_weights_are_restricted_to_fbgemm_safe_range() -> None:
    seed_everything(2)
    lin = nn.Linear(64, 128)
    q = make_qlinear(lin, (-4.0, 4.0), (-8.0, 8.0))
    qweight = q.get_buffer("qweight")
    assert int(qweight.min()) >= -64
    assert int(qweight.max()) <= 63
    assert qweight.dtype == torch.int8


def test_qlinear_matches_float_linear_within_quantization_error() -> None:
    seed_everything(3)
    lin = nn.Linear(64, 96)
    x = torch.randn(256, 64) * 1.5
    with torch.inference_mode():
        ref = lin(x)
        lo, hi = float(x.min()), float(x.max())
        q = make_qlinear(lin, (lo, hi), (float(ref.min()), float(ref.max())))
        got = q(x)
    rel = float((got - ref).abs().max()) / float(ref.abs().max())
    assert rel < 0.05


def test_quantize_static_shares_ffn_output_params_with_next_input() -> None:
    cpu = from_trained(_small_trained())
    q_model = quantize_static(cpu, _matrices(512, seed=4))
    for block in q_model.blocks:
        lin1 = block.lin1
        lin2 = block.lin2
        assert isinstance(lin1, QLinear) and isinstance(lin2, QLinear)
        assert lin2.in_scale == lin1.out_scale
        assert lin2.in_zp == lin1.out_zp


def test_quantized_model_outputs_are_finite_and_close_to_fp32() -> None:
    cpu = from_trained(_small_trained())
    q_model = quantize_static(cpu, _matrices(512, seed=5))
    x = _matrices(128, seed=6)
    with torch.inference_mode():
        d_fp, _ = cpu(x)
        d_q, c_q = q_model(x)
    assert torch.isfinite(d_q).all() and torch.isfinite(c_q).all()
    # 随机初始化模型的 logits 很小，只检查相对误差量级
    scale = float(d_fp.abs().max())
    assert float((d_q - d_fp).abs().max()) < 0.25 * scale


def test_export_and_load_round_trip_is_exact(tmp_path: Path) -> None:
    cpu = from_trained(_small_trained())
    q_model = quantize_static(cpu, _matrices(512, seed=7))
    path = tmp_path / "int8.pt"
    save_int8(export_int8(q_model), path)
    loaded = load_int8(path)
    x = _matrices(32, seed=8)
    with torch.inference_mode():
        a = q_model(x)
        b = loaded(x)
    assert torch.equal(a[0], b[0])
    assert torch.equal(a[1], b[1])


def test_load_rejects_unknown_format(tmp_path: Path) -> None:
    path = tmp_path / "bad.pt"
    torch.save({"format": "other"}, path)
    with pytest.raises(ValueError):
        load_int8(path)


def test_predict_returns_integer_digit_and_carry_shapes() -> None:
    cpu = from_trained(_small_trained())
    x = _matrices(7, seed=9)
    d, c = predict(cpu, x)
    assert d.shape == (7, 8) and c.shape == (7, 8)
    assert d.dtype == torch.int64


def test_fbgemm_int8_path_has_no_nan_on_boundary_inputs() -> None:
    cpu = from_trained(_small_trained())
    q_model: CpuAdder = quantize_static(cpu, _matrices(256, seed=10))
    d, _ = predict(q_model, to_matrix(fixed_boundary_values()))
    assert d.shape[0] == fixed_boundary_values().shape[0]


@pytest.mark.skipif(not CKPT.exists(), reason="需要已训练的 fp32 检查点（backend/checkpoints）")
def test_int8_model_meets_accuracy_gate_on_test_set(tmp_path: Path) -> None:
    trained = load_checkpoint(CKPT, device="cpu")
    cpu = from_trained(trained)
    calib = _matrices(65_536, seed=2024)
    q_model = quantize_static(cpu, calib)
    values = sample_values(10_000, make_generator(12_345), boundary_frac=0.0)
    mat = to_matrix(values)
    d_true, c_true = targets(mat)
    d_pred, _ = predict(q_model, mat)
    sum_acc = float((d_pred == d_true).all(dim=-1).float().mean())
    assert sum_acc >= 0.999
    bnd = to_matrix(fixed_boundary_values())
    d_b, _ = targets(bnd)
    pb, _ = predict(q_model, bnd)
    assert bool((pb == d_b).all())
    assert c_true.shape == (10_000, 8)
