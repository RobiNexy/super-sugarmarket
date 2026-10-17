"""面向 CPU 的竖式加法推理图与静态 W8A8 int8 量化。

@purpose 把训练模型转换为仅含 nn.Linear/LayerNorm 的推理图；线性层可替换为真 int8 GEMM
（fbgemm），用于 CPU 上的批量推理。
@spec [[adder-cpu-int8-inference]]
@invariants fp32 推理图与训练模型 logits 一致（误差 < 1e-4）；int8 线性层权重位于 [-64, 63]
（fbgemm 饱和限制）；激活使用校准得到的固定 quint8 仿射参数；FFN 第二层输入与第一层输出
参数相同，ReLU 在 quint8 上执行。
@adr [[ADR-0004-cpu-int8-inference]]
@touches 被 backend/adder/cpu_deploy.py 使用；训练代码不依赖本文件。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import cast

import torch
from torch import nn

from adder.data import COLS, ROWS, SUM_CLASSES
from adder.model import AdderTransformer, ModelConfig

INT8_FORMAT = "adder-cpu-int8-v1"

# fbgemm(AVX2) 的 uint8×int8 成对求和会在 int16 中饱和，权重需限制在 [-64, 63]（即 reduce_range）。
QW_MIN = -64
QW_MAX = 63
UINT8_LEVELS = 255
_PRIVATE_MAKE_QT = "_make_per_channel_quantized_tensor"


class QLinear(nn.Module):
    """静态 int8 线性层。输入/输出为 fp32；内部 quint8 激活 × qint8 权重，经 fbgemm 计算。"""

    def __init__(
        self,
        qweight: torch.Tensor,
        w_scale: torch.Tensor,
        bias: torch.Tensor,
        in_scale: float,
        in_zp: int,
        out_scale: float,
        out_zp: int,
    ) -> None:
        super().__init__()
        if qweight.dtype != torch.int8:
            raise ValueError("qweight must be int8")
        self.in_features = int(qweight.shape[1])
        self.out_features = int(qweight.shape[0])
        self.in_scale = float(in_scale)
        self.in_zp = int(in_zp)
        self.out_scale = float(out_scale)
        self.out_zp = int(out_zp)
        qw = qweight.detach().clone().contiguous()
        ws = w_scale.detach().clone().to(torch.float32)
        bs = bias.detach().clone().to(torch.float32)
        self.register_buffer("qweight", qw)
        self.register_buffer("w_scale", ws)
        self.register_buffer("bias", bs)
        self.packed: object = _prepack(qw, ws, bs)

    def quantize_input(self, x2d: torch.Tensor) -> torch.Tensor:
        return torch.quantize_per_tensor(x2d, self.in_scale, self.in_zp, torch.quint8)

    def forward_q(self, xq2d: torch.Tensor) -> torch.Tensor:
        """quint8 输入 -> quint8 输出，供相邻量化算子直接衔接。"""
        return torch.ops.quantized.linear(xq2d, self.packed, self.out_scale, self.out_zp)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        shape = x.shape[:-1]
        x2 = x.reshape(-1, self.in_features)
        yq = self.forward_q(self.quantize_input(x2))
        return yq.dequantize().reshape(*shape, self.out_features)


def _prepack(qweight: torch.Tensor, w_scale: torch.Tensor, bias: torch.Tensor) -> object:
    # 直接包装已量化的 int8 值，不做二次量化
    # TODO(types): torch._make_per_channel_quantized_tensor 为私有 API 且存根缺失，无公开替代
    make_qt = cast(Callable[..., torch.Tensor], getattr(torch, _PRIVATE_MAKE_QT))
    qw = make_qt(
        qweight.contiguous(),
        w_scale.to(torch.float64).contiguous(),
        torch.zeros(qweight.shape[0], dtype=torch.int64),
        0,
    )
    prepack = cast(
        Callable[[torch.Tensor, torch.Tensor], object], torch.ops.quantized.linear_prepack
    )
    return prepack(qw, bias.to(torch.float32))


class _Block(nn.Module):
    def __init__(self, d_model: int, n_heads: int, d_ff: int) -> None:
        super().__init__()
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.qkv: nn.Module = nn.Linear(d_model, 3 * d_model)
        self.out: nn.Module = nn.Linear(d_model, d_model)
        self.lin1: nn.Module = nn.Linear(d_model, d_ff)
        self.lin2: nn.Module = nn.Linear(d_ff, d_model)
        self.norm1 = nn.LayerNorm(d_model, eps=1e-5)
        self.norm2 = nn.LayerNorm(d_model, eps=1e-5)

    def forward(self, h: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        b, t, d = h.shape
        qkv = self.qkv(h).reshape(b, t, 3, self.n_heads, self.head_dim)
        q, k, v = qkv.permute(2, 0, 3, 1, 4).unbind(0)  # 每个 [B, H, T, dh]
        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        attn = torch.softmax(scores + mask, dim=-1)
        ctx = torch.matmul(attn, v).transpose(1, 2).reshape(b, t, d)
        h = self.norm1(h + self.out(ctx))
        h = self.norm2(h + self._ffn(h))
        return h

    def _ffn(self, h: torch.Tensor) -> torch.Tensor:
        shape = h.shape
        h2 = h.reshape(-1, shape[-1])
        if isinstance(self.lin1, QLinear) and isinstance(self.lin2, QLinear):
            hq = torch.relu(self.lin1.forward_q(self.lin1.quantize_input(h2)))
            y = self.lin2.forward_q(hq).dequantize()
        else:
            y = self.lin2(torch.relu(self.lin1(h2)))
        return y.reshape(shape)


class CpuAdder(nn.Module):
    """与 AdderTransformer 等价的推理图；线性层可替换为 QLinear。"""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.config = config
        self.sum_embedding = nn.Embedding(SUM_CLASSES, config.d_model)
        self.column_embedding = nn.Embedding(COLS, config.d_model)
        self.blocks = nn.ModuleList(
            _Block(config.d_model, config.n_heads, config.d_ff) for _ in range(config.n_layers)
        )
        self.digit_head: nn.Module = nn.Linear(config.d_model, 10)
        self.carry_head: nn.Module = nn.Linear(config.d_model, 10)
        causal = torch.triu(torch.full((COLS, COLS), float("-inf")), diagonal=1)
        self.register_buffer("causal_mask", causal, persistent=False)
        self.register_buffer("positions", torch.arange(COLS), persistent=False)

    def forward(self, matrix: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """matrix: [B, 10, 8] 整数张量。返回 (digit_logits [B,8,10], carry_logits [B,8,10])。"""
        # 导出追踪时跳过形状判断（TracerWarning）；torch.jit.is_tracing 存根不导出
        if not torch.jit.is_tracing() and matrix.shape[1:] != (ROWS, COLS):  # pyright: ignore[reportPrivateImportUsage]
            raise ValueError(f"expected [B, {ROWS}, {COLS}], got {tuple(matrix.shape)}")
        sigma = matrix.sum(dim=1)
        h = self.sum_embedding(sigma) + self.column_embedding(self.positions)
        for block in self.blocks:
            block_mod = cast(_Block, block)
            h = block_mod(h, self.causal_mask)
        return self.digit_head(h), self.carry_head(h)


def from_state_dict(state: dict[str, torch.Tensor], config: ModelConfig) -> CpuAdder:
    """把 AdderTransformer 的 fp32 state_dict（nn.TransformerEncoder 键名）转换为 CpuAdder。"""
    model = CpuAdder(config)
    new: dict[str, torch.Tensor] = {
        "sum_embedding.weight": state["sum_embedding.weight"],
        "column_embedding.weight": state["column_embedding.weight"],
        "digit_head.weight": state["digit_head.weight"],
        "digit_head.bias": state["digit_head.bias"],
        "carry_head.weight": state["carry_head.weight"],
        "carry_head.bias": state["carry_head.bias"],
    }
    for i in range(config.n_layers):
        src = f"encoder.layers.{i}."
        dst = f"blocks.{i}."
        pairs = {
            "qkv.weight": "self_attn.in_proj_weight",
            "qkv.bias": "self_attn.in_proj_bias",
            "out.weight": "self_attn.out_proj.weight",
            "out.bias": "self_attn.out_proj.bias",
            "lin1.weight": "linear1.weight",
            "lin1.bias": "linear1.bias",
            "lin2.weight": "linear2.weight",
            "lin2.bias": "linear2.bias",
            "norm1.weight": "norm1.weight",
            "norm1.bias": "norm1.bias",
            "norm2.weight": "norm2.weight",
            "norm2.bias": "norm2.bias",
        }
        for dst_key, src_key in pairs.items():
            new[dst + dst_key] = state[src + src_key]
    model.load_state_dict(new)
    model.eval()
    return model


def from_trained(model: AdderTransformer) -> CpuAdder:
    return from_state_dict(dict(model.state_dict()), model.config)


def affine_params(lo: float, hi: float) -> tuple[float, int]:
    """由观测范围求 quint8 的 (scale, zero_point)；范围强制包含 0。"""
    lo = min(lo, 0.0)
    hi = max(hi, 0.0)
    scale = max((hi - lo) / UINT8_LEVELS, 1e-12)
    zp = int(round(-lo / scale))
    return scale, min(max(zp, 0), UINT8_LEVELS)


def quantize_weight_rows(w: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """每输出行对称量化到 [-64, 63]。返回 (int8 [out,in], fp32 scale [out])。"""
    scale = w.abs().amax(dim=1).clamp_min(1e-12) / QW_MAX
    q = torch.clamp(torch.round(w / scale[:, None]), QW_MIN, QW_MAX).to(torch.int8)
    return q, scale


def make_qlinear(
    lin: nn.Linear, in_range: tuple[float, float], out_range: tuple[float, float]
) -> QLinear:
    q, scale = quantize_weight_rows(lin.weight.detach().to(torch.float32))
    in_s, in_zp = affine_params(*in_range)
    out_s, out_zp = affine_params(*out_range)
    return QLinear(q, scale, lin.bias.detach().to(torch.float32), in_s, in_zp, out_s, out_zp)


Range = tuple[float, float]


def _named_modules(model: nn.Module) -> list[tuple[str, nn.Module]]:
    # TODO(types): torch 存根中 named_modules 返回 partially unknown，显式收窄类型
    return list(cast(Iterable[tuple[str, nn.Module]], model.named_modules()))


def calibrate_ranges(
    model: CpuAdder, calib: torch.Tensor, batch: int = 4096
) -> dict[str, tuple[Range, Range]]:
    """记录每个 nn.Linear 的输入与输出观测范围。calib: [N, 10, 8] 整数矩阵。"""
    stats: dict[str, list[float]] = {}
    handles: list[torch.utils.hooks.RemovableHandle] = []
    for name, mod in _named_modules(model):
        if isinstance(mod, nn.Linear):
            stats[name] = [float("inf"), float("-inf"), float("inf"), float("-inf")]

            def hook(
                _module: nn.Module,
                inputs: tuple[torch.Tensor, ...],
                output: torch.Tensor,
                key: str = name,
            ) -> None:
                s = stats[key]
                x = inputs[0].detach()
                s[0] = min(s[0], float(x.min()))
                s[1] = max(s[1], float(x.max()))
                s[2] = min(s[2], float(output.min()))
                s[3] = max(s[3], float(output.max()))

            handles.append(mod.register_forward_hook(hook))
    try:
        model.eval()
        with torch.inference_mode():
            for i in range(0, calib.shape[0], batch):
                model(calib[i : i + batch])
    finally:
        for h in handles:
            h.remove()
    return {k: ((v[0], v[1]), (v[2], v[3])) for k, v in stats.items()}


def quantize_static(model: CpuAdder, calib: torch.Tensor) -> CpuAdder:
    """返回所有线性层替换为 QLinear 的新模型（输入模型不变）。"""
    ranges = calibrate_ranges(model, calib)
    # FFN 第二层输入与第一层输出共用校准范围，使两者 quint8 参数完全相同
    for name in list(ranges):
        if name.endswith(".lin2"):
            lin1_out = ranges[name[: -len("lin2")] + "lin1"][1]
            ranges[name] = (lin1_out, ranges[name][1])
    qmodel = CpuAdder(model.config)
    qmodel.load_state_dict(model.state_dict())
    qmodel.eval()
    for name, mod in _named_modules(qmodel):
        if isinstance(mod, nn.Linear):
            in_r, out_r = ranges[name]
            qmodel.set_submodule(name, make_qlinear(mod, in_r, out_r))
    return qmodel


def qlinear_names(model: nn.Module) -> dict[str, QLinear]:
    out: dict[str, QLinear] = {}
    for name, mod in _named_modules(model):
        if isinstance(mod, QLinear):
            out[name] = mod
    return out


def export_int8(model: CpuAdder) -> dict[str, object]:
    """把静态 int8 模型序列化为可部署字典：int8 权重、scale、bias、激活参数与 fp32 其余参数。"""
    layers = qlinear_names(model)
    if not layers:
        raise ValueError("model has no QLinear layers; call quantize_static first")
    params: dict[str, dict[str, float | int]] = {
        name: {
            "in_scale": q.in_scale,
            "in_zp": q.in_zp,
            "out_scale": q.out_scale,
            "out_zp": q.out_zp,
        }
        for name, q in layers.items()
    }
    return {
        "format": INT8_FORMAT,
        "config": {
            "d_model": model.config.d_model,
            "n_layers": model.config.n_layers,
            "n_heads": model.config.n_heads,
            "d_ff": model.config.d_ff,
            "dropout": model.config.dropout,
        },
        "qlinear_params": params,
        "state": dict(model.state_dict()),
    }


def save_int8(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)


def load_int8(path: Path) -> CpuAdder:
    payload = cast(dict[str, object], torch.load(path, map_location="cpu", weights_only=True))
    if payload.get("format") != INT8_FORMAT:
        raise ValueError(f"unsupported int8 format: {payload.get('format')}")
    raw_cfg = cast(dict[str, float], payload["config"])
    cfg = ModelConfig(
        d_model=int(raw_cfg["d_model"]),
        n_layers=int(raw_cfg["n_layers"]),
        n_heads=int(raw_cfg["n_heads"]),
        d_ff=int(raw_cfg["d_ff"]),
        dropout=float(raw_cfg["dropout"]),
    )
    state = cast(dict[str, torch.Tensor], payload["state"])
    params = cast(dict[str, dict[str, float]], payload["qlinear_params"])
    model = CpuAdder(cfg)
    for name, p in params.items():
        model.set_submodule(
            name,
            QLinear(
                state[f"{name}.qweight"],
                state[f"{name}.w_scale"],
                state[f"{name}.bias"],
                p["in_scale"],
                int(p["in_zp"]),
                p["out_scale"],
                int(p["out_zp"]),
            ),
        )
    model.load_state_dict(state)
    model.eval()
    return model


def predict(model: CpuAdder, matrix: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """返回 (数字 [B,8], 进位 [B,8])，均为 argmax 结果（int64）。"""
    with torch.inference_mode():
        digit_logits, carry_logits = model(matrix)
    return digit_logits.argmax(dim=-1), carry_logits.argmax(dim=-1)
