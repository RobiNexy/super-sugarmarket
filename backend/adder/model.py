"""竖式列加法 Transformer 模型。

@purpose 以列和为充分统计量，用因果 Transformer 逐列预测和的数字与下一进位。
@spec [[adder-transformer-column-addition-training]]
@invariants 行置换不变（列和对行求和）；列注意力因果（第 i 列只看 0..i）；
输出 8 列数字与进位 logits。
@adr [[ADR-0002-pytorch-local-cuda-training]]
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypedDict

import torch
from torch import nn

from adder.data import COLS, ROWS, SUM_CLASSES


@dataclass(frozen=True)
class ModelConfig:
    d_model: int = 64
    n_layers: int = 2
    n_heads: int = 4
    d_ff: int = 256
    dropout: float = 0.0


class AdderOutput(TypedDict):
    digit_logits: torch.Tensor  # [B, 8, 10]
    carry_logits: torch.Tensor  # [B, 8, 10]


class AdderTransformer(nn.Module):
    def __init__(self, config: ModelConfig | None = None) -> None:
        super().__init__()
        cfg = config or ModelConfig()
        self.config = cfg
        self.sum_embedding = nn.Embedding(SUM_CLASSES, cfg.d_model)
        self.column_embedding = nn.Embedding(COLS, cfg.d_model)
        layer = nn.TransformerEncoderLayer(
            d_model=cfg.d_model,
            nhead=cfg.n_heads,
            dim_feedforward=cfg.d_ff,
            dropout=cfg.dropout,
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            layer, num_layers=cfg.n_layers, enable_nested_tensor=False
        )
        self.digit_head = nn.Linear(cfg.d_model, 10)
        self.carry_head = nn.Linear(cfg.d_model, 10)

        causal = torch.triu(torch.ones(COLS, COLS, dtype=torch.bool), diagonal=1)
        self.register_buffer("causal_mask", causal, persistent=False)
        self.register_buffer("positions", torch.arange(COLS), persistent=False)

    def forward(self, matrix: torch.Tensor) -> AdderOutput:
        """matrix: [B, 10, 8] 数字张量（LongTensor，取值 0..9，最高列为 0）。"""
        if matrix.shape[1:] != (ROWS, COLS):
            raise ValueError(f"expected [B, {ROWS}, {COLS}], got {tuple(matrix.shape)}")
        sigma = matrix.sum(dim=1)  # [B, 8]，对行求和使输出行置换不变
        h = self.sum_embedding(sigma) + self.column_embedding(self.positions)
        h = self.encoder(h, mask=self.causal_mask)
        return {
            "digit_logits": self.digit_head(h),
            "carry_logits": self.carry_head(h),
        }


def adder_loss(
    output: AdderOutput,
    digits: torch.Tensor,
    carries: torch.Tensor,
    carry_weight: float = 1.0,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """返回 (总损失, 数字损失, 进位损失)。digits/carries: [B, 8] 长整型真值。"""
    digit_loss = nn.functional.cross_entropy(
        output["digit_logits"].reshape(-1, 10), digits.reshape(-1)
    )
    carry_loss = nn.functional.cross_entropy(
        output["carry_logits"].reshape(-1, 10), carries.reshape(-1)
    )
    return digit_loss + carry_weight * carry_loss, digit_loss, carry_loss


class Checkpoint(TypedDict):
    config: dict[str, int | float]
    model_state: dict[str, torch.Tensor]


def save_checkpoint(model: AdderTransformer, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Checkpoint = {
        "config": dict(asdict(model.config)),
        "model_state": model.state_dict(),
    }
    torch.save(payload, path)


def config_from_mapping(raw: Mapping[str, int | float]) -> ModelConfig:
    return ModelConfig(
        d_model=int(raw["d_model"]),
        n_layers=int(raw["n_layers"]),
        n_heads=int(raw["n_heads"]),
        d_ff=int(raw["d_ff"]),
        dropout=float(raw["dropout"]),
    )


def load_checkpoint(path: Path, device: torch.device | str = "cpu") -> AdderTransformer:
    payload: Checkpoint = torch.load(path, map_location=device, weights_only=True)
    model = AdderTransformer(config_from_mapping(payload["config"]))
    model.load_state_dict(payload["model_state"])
    model.to(device)
    model.eval()
    return model
