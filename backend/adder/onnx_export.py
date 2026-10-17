"""把竖式加法模型导出为 ONNX，并与 PyTorch 训练图做一致性校验。

@purpose 生成可被 ONNX Runtime 加载的 fp32 模型文件（batch 维动态），并校验其 argmax 与训练图一致。
@spec [[adder-onnx-cpu-inference]]
@invariants 导出图的输入名为 matrix，输出为 digits 与 carries（logits）；通过 onnx.checker；
与训练图在校验集上 argmax 逐条一致且 logit 最大差 < 1e-4。
@adr [[ADR-0005-onnx-runtime-cpu-deployment]]

用法（在 backend/ 下）：
    uv run --group train python -m adder.onnx_export --ckpt checkpoints/adder/adder-final.pt \\
        --out checkpoints/adder-onnx/adder.onnx
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import onnx  # pyright: ignore[reportMissingTypeStubs]
import torch
from torch import nn

from adder.data import COLS, ROWS, make_generator, sample_values, targets, to_matrix
from adder.infer import CpuAdder, from_trained
from adder.model import AdderTransformer, load_checkpoint
from adder.onnx_runtime import OnnxAdder

OPSET = 17
_EXPORT = "export"
INPUT_NAME = "matrix"
OUTPUT_NAMES = ["digits", "carries"]


class _ExportWrapper(nn.Module):
    def __init__(self, inner: CpuAdder) -> None:
        super().__init__()
        self.inner = inner

    def forward(self, matrix: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return self.inner(matrix)


def export_onnx(model: CpuAdder, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros(2, ROWS, COLS, dtype=torch.int64)
    # TODO(types): torch.onnx.export 存根对 dynamic_axes 返回类型不完整，上游问题
    export_fn: Any = getattr(torch.onnx, _EXPORT)
    with torch.inference_mode():
        export_fn(
            _ExportWrapper(model).eval(),
            (dummy,),
            str(out_path),
            input_names=[INPUT_NAME],
            output_names=OUTPUT_NAMES,
            dynamic_axes={
                INPUT_NAME: {0: "batch"},
                OUTPUT_NAMES[0]: {0: "batch"},
                OUTPUT_NAMES[1]: {0: "batch"},
            },
            opset_version=OPSET,
            dynamo=False,
        )


def check_onnx_file(path: Path) -> None:
    model = onnx.load(str(path))  # pyright: ignore[reportUnknownMemberType]
    onnx.checker.check_model(model, full_check=True)  # pyright: ignore[reportUnknownMemberType]


def verify_against_torch(
    model: AdderTransformer, onnx_path: Path, n: int = 20_000
) -> dict[str, float]:
    """在 n 条随机矩阵上比较 ORT 与训练图：argmax 一致率与 logit 最大差。"""
    values = sample_values(n, make_generator(4242), boundary_frac=0.1)
    mat = to_matrix(values)
    with torch.inference_mode():
        out = model(mat)
    d_t = out["digit_logits"].numpy()
    c_t = out["carry_logits"].numpy()
    mat_np = mat.numpy()
    adder = OnnxAdder(onnx_path, threads=1)
    d_o, c_o = adder.logits(mat_np)
    digit_match = float((d_o.argmax(-1) == d_t.argmax(-1)).all(-1).mean())
    carry_match = float((c_o.argmax(-1) == c_t.argmax(-1)).all(-1).mean())
    max_logit = max(float(np.abs(d_o - d_t).max()), float(np.abs(c_o - c_t).max()))
    d_true, _ = targets(mat)
    sum_acc = float((d_o.argmax(-1) == d_true.numpy()).all(-1).mean())
    return {
        "samples": float(n),
        "digit_argmax_match": digit_match,
        "carry_argmax_match": carry_match,
        "max_abs_logit_diff": max_logit,
        "sum_acc": sum_acc,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="导出竖式加法模型为 ONNX 并校验")
    parser.add_argument("--ckpt", default="checkpoints/adder/adder-final.pt")
    parser.add_argument("--out", default="checkpoints/adder-onnx/adder.onnx")
    args = parser.parse_args()
    ckpt = Path(args.ckpt)
    out = Path(args.out)
    trained = load_checkpoint(ckpt, device="cpu")
    export_onnx(from_trained(trained), out)
    check_onnx_file(out)
    report = verify_against_torch(trained, out)
    print(report, flush=True)
    if report["digit_argmax_match"] < 1.0 or report["carry_argmax_match"] < 1.0:
        raise SystemExit("ONNX 与训练图 argmax 不一致")
    if report["max_abs_logit_diff"] >= 1e-4:
        raise SystemExit("ONNX 与训练图 logit 差超过 1e-4")
    print(f"exported and verified: {out}")


if __name__ == "__main__":
    main()
