"""小批量 CPU 推理基准：ONNX Runtime（含封装开销）对比 PyTorch 图。

@purpose 以小批量（1–16）为主，测量各推理路径的中位延迟，并生成运行手册报告。
@spec [[adder-onnx-cpu-inference]]
@invariants 所有路径使用同一批随机矩阵；每个 (路径, 线程, batch) 组合先预热再计时；
报告数字全部由脚本计算。

用法（在 backend/ 下，隐藏 GPU）：
    CUDA_VISIBLE_DEVICES= uv run --group train python -m adder.onnx_bench \\
        --report ../agent-knowledge/operations-runbook/adder-onnx-cpu-inference-report.md
"""

from __future__ import annotations

import argparse
import statistics
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, cast

import numpy as np
import torch

from adder.data import make_generator, sample_values, to_matrix
from adder.infer import CpuAdder, from_trained
from adder.model import AdderTransformer, load_checkpoint
from adder.onnx_runtime import OnnxAdder

BATCHES = (1, 2, 4, 16, 256)
THREADS = (1, 6)


def _reps(batch: int) -> int:
    return 1000 if batch <= 4 else 400 if batch <= 16 else 40


def _median_ms(fn: Callable[[], object], reps: int) -> float:
    for _ in range(20):
        fn()
    ts: list[float] = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts) * 1e3


def _cpu_name() -> str:
    for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return "unknown"


_COMPILE = "compile"


def _compile(model: torch.nn.Module) -> Callable[[torch.Tensor], object]:
    # TODO(types): torch.compile 存根返回 partially unknown，显式收窄
    compile_fn = cast(Callable[..., Callable[[torch.Tensor], object]], getattr(torch, _COMPILE))
    return compile_fn(model, dynamic=False)


def run(ckpt: Path, onnx_path: Path) -> dict[str, Any]:
    trained = load_checkpoint(ckpt, device="cpu")
    cpu_graph = from_trained(trained)
    results: dict[str, Any] = {}
    x_all = to_matrix(sample_values(max(BATCHES), make_generator(77), boundary_frac=0.0))
    x_np_all = x_all.numpy()
    for threads in THREADS:
        torch.set_num_threads(threads)
        ort_adder = OnnxAdder(onnx_path, threads=threads)
        compiled = _compile(cpu_graph)
        paths = _make_paths(trained, cpu_graph, compiled, ort_adder, x_all, x_np_all)
        for label, make_fn in paths.items():
            for b in BATCHES:
                fn = make_fn(b)
                with torch.inference_mode():
                    ms = _median_ms(fn, _reps(b))
                results.setdefault(str(threads), {}).setdefault(label, {})[str(b)] = ms
                print(f"threads={threads} {label} batch={b}: {ms:.4f} ms", flush=True)
    return results


def _make_paths(
    trained: AdderTransformer,
    cpu_graph: CpuAdder,
    compiled: Callable[[torch.Tensor], object],
    ort_adder: OnnxAdder,
    x_all: torch.Tensor,
    x_np_all: np.ndarray,
) -> dict[str, Callable[[int], Callable[[], object]]]:
    def torch_fn(
        model: Callable[[torch.Tensor], object],
    ) -> Callable[[int], Callable[[], object]]:
        return lambda b: lambda: model(x_all[:b])

    def ort_predict(b: int) -> Callable[[], object]:
        return lambda: ort_adder.predict(x_np_all[:b])

    def ort_raw(b: int) -> Callable[[], object]:
        x = x_np_all[:b]
        sess = ort_adder.session
        return lambda: sess.run(None, {"matrix": x})

    return {
        "PyTorch 训练图": torch_fn(trained),
        "PyTorch CPU 推理图": torch_fn(cpu_graph),
        "PyTorch CPU 推理图 + torch.compile": torch_fn(compiled),
        "ORT 封装 predict（含校验）": ort_predict,
        "ORT 原始 session.run（无校验）": ort_raw,
    }


def render(results: dict[str, Any], ckpt: Path, onnx_path: Path, report: Path) -> None:
    lines: list[str] = [
        "# 竖式加法模型 ONNX Runtime 小批量推理报告",
        "",
        f"生成日期：{date.today().isoformat()}  ",
        f"CPU：{_cpu_name()}；torch {torch.__version__}  ",
        "对应规格：[[adder-onnx-cpu-inference]]；决策：[[ADR-0005-onnx-runtime-cpu-deployment]]",
        "",
        "## 1. 操作步骤",
        "",
        "1. 确认检查点存在：`backend/checkpoints/adder/adder-final.pt`。",
        "2. 导出并校验 ONNX（在 backend/ 下）：",
        "   ```sh",
        "   uv run --group train python -m adder.onnx_export "
        "--ckpt checkpoints/adder/adder-final.pt "
        "--out checkpoints/adder-onnx/adder.onnx",
        "   ```",
        "3. 运行小批量基准（隐藏 GPU 以保证 CPU 测量纯净）：",
        "   ```sh",
        "   CUDA_VISIBLE_DEVICES= uv run --group train python -m adder.onnx_bench \\",
        "       --report ../agent-knowledge/operations-runbook/adder-onnx-cpu-inference-report.md",
        "   ```",
        "4. 验证：`uv run --group train pytest`、`uv run ruff check .`、"
        "`uv run --group train pyright`。",
        "",
        "## 2. 文件",
        "",
        f"- 检查点：`{ckpt}`",
        f"- ONNX 模型：`{onnx_path}`，大小 {onnx_path.stat().st_size / 1024:.1f} KiB",
        "",
        "## 3. 中位延迟（ms，越低越好）",
        "",
    ]
    labels = list(next(iter(results.values())).keys())
    for threads, per_label in results.items():
        lines.append(f"### {threads} 线程")
        lines.append("")
        lines.append("| 路径 | " + " | ".join(f"batch {b}" for b in BATCHES) + " |")
        lines.append("|---|" + "---|" * len(BATCHES))
        for label in labels:
            row = per_label[label]
            lines.append(f"| {label} | " + " | ".join(f"{row[str(b)]:.4f}" for b in BATCHES) + " |")
        lines.append("")
        base = per_label["PyTorch CPU 推理图"]
        onnx_row = per_label["ORT 封装 predict（含校验）"]
        lines.append(
            "相对 PyTorch CPU 推理图（同线程）："
            + "，".join(f"batch {b} ×{base[str(b)] / onnx_row[str(b)]:.2f}" for b in BATCHES)
            + "。"
        )
        lines.append("")
    lines += [
        "## 4. 局限与未测项",
        "",
        "- 测量的是模型前向（含或不含封装校验），不含 tree_sum、金额格式化与 HTTP 开销。",
        "- 测试机为 Broadwell Xeon（AVX2）；其他 CPU 的相对结果可能不同。",
        "- 精度见 `adder/onnx_export.py` 的校验输出与测试；"
        "ONNX 与训练图的 argmax 一致性由导出时校验。",
        "- 导出使用 PyTorch 的 TorchScript 导出器（`dynamo=False`），"
        "PyTorch 新版本已将其标记为弃用，升级时需回归。",
        "",
    ]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="ONNX Runtime 小批量推理基准")
    parser.add_argument("--ckpt", default="checkpoints/adder/adder-final.pt")
    parser.add_argument("--onnx", default="checkpoints/adder-onnx/adder.onnx")
    parser.add_argument(
        "--report",
        default="../agent-knowledge/operations-runbook/adder-onnx-cpu-inference-report.md",
    )
    args = parser.parse_args()
    ckpt = Path(args.ckpt)
    onnx_path = Path(args.onnx)
    results = run(ckpt, onnx_path)
    render(results, ckpt, onnx_path, Path(args.report))
    print(f"report written to {args.report}")


if __name__ == "__main__":
    main()
