"""竖式列加法模型的结构性质与训练流程测试。

@purpose 验证行置换不变、列因果性、检查点往返与 CPU 训练可复现。
@spec [[adder-transformer-column-addition-training]]
@covers adder/model.py（前向、损失、检查点）、adder/train.py（train/evaluate）
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import torch

from adder.data import ROWS, make_generator, sample_values, seed_everything, targets, to_matrix
from adder.model import AdderTransformer, ModelConfig, adder_loss, load_checkpoint, save_checkpoint
from adder.train import TrainConfig, train

SMALL = ModelConfig(d_model=32, n_layers=1, n_heads=2, d_ff=64, dropout=0.0)


def _random_matrix(batch: int, seed: int) -> torch.Tensor:
    gen = make_generator(seed)
    return to_matrix(sample_values(batch, gen, boundary_frac=0.0))


def test_output_is_invariant_to_row_permutation() -> None:
    seed_everything(0)
    model = AdderTransformer(SMALL).eval()
    matrix = _random_matrix(16, seed=1)
    perm = torch.randperm(ROWS)
    with torch.inference_mode():
        a = model(matrix)
        b = model(matrix[:, perm, :])
    assert torch.allclose(a["digit_logits"], b["digit_logits"])
    assert torch.allclose(a["carry_logits"], b["carry_logits"])


def test_column_attention_is_causal() -> None:
    seed_everything(0)
    model = AdderTransformer(SMALL).eval()
    matrix = _random_matrix(8, seed=2)
    changed = matrix.clone()
    changed[:, :, 5] = (changed[:, :, 5] + 1) % 10  # 只改第 5 列（最高列保持 0）
    with torch.inference_mode():
        base = model(matrix)
        other = model(changed)
    # 第 0..4 列只能看见 0..i 列，因而不受第 5 列改动影响
    for col in range(5):
        assert torch.allclose(base["digit_logits"][:, col], other["digit_logits"][:, col])
        assert torch.allclose(base["carry_logits"][:, col], other["carry_logits"][:, col])


def test_loss_is_finite_and_reports_components() -> None:
    seed_everything(0)
    model = AdderTransformer(SMALL)
    matrix = _random_matrix(4, seed=3)
    digits, carries = targets(matrix)
    total, d_loss, c_loss = adder_loss(model(matrix), digits, carries, carry_weight=1.0)
    assert torch.isfinite(total)
    assert torch.allclose(total, d_loss + c_loss)


def test_checkpoint_round_trip_preserves_outputs(tmp_path: Path) -> None:
    seed_everything(0)
    model = AdderTransformer(SMALL).eval()
    path = tmp_path / "ckpt.pt"
    save_checkpoint(model, path)
    loaded = load_checkpoint(path, device="cpu")
    matrix = _random_matrix(4, seed=4)
    with torch.inference_mode():
        a = model(matrix)
        b = loaded(matrix)
    assert torch.equal(a["digit_logits"], b["digit_logits"])
    assert loaded.config == model.config


def test_cpu_training_is_reproducible_and_writes_report(tmp_path: Path) -> None:
    cfg = TrainConfig(
        steps=10,
        batch_size=32,
        log_every=5,
        eval_every=1000,
        eval_size=256,
        device="cpu",
        out_dir=str(tmp_path / "run"),
    )
    first = train(cfg, model_cfg=SMALL)
    second = train(replace(cfg, out_dir=str(tmp_path / "run2")), model_cfg=SMALL)
    h1 = _losses(first)
    h2 = _losses(second)
    assert len(h1) == 2
    assert h1 == h2
    assert (tmp_path / "run" / "adder-final.pt").exists()
    assert (tmp_path / "run" / "report.json").exists()


def _losses(report: dict[str, object]) -> list[float]:
    history = cast(list[dict[str, float]], report["history"])
    return [entry["loss"] for entry in history]
