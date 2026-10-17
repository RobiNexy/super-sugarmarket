"""CPU 部署流水线：校准、导出 int8、精度评估、推理基准与报告生成。

@purpose 从 fp32 检查点生成静态 W8A8 CPU 推理模型，并在同一批数据上比较精度与延迟/吞吐。
@spec [[adder-cpu-int8-inference]]
@invariants 评估集与 train.py 一致（测试集种子 12345，大样本种子 777）；
校准集与训练分布一致但种子独立（2024）；报告数字全部由脚本计算。

运行（建议在 CPU-only 环境下，避免与 GPU 训练争用）：
    CUDA_VISIBLE_DEVICES= uv run --group train python -m adder.cpu_deploy \\
        --report ../agent-knowledge/operations-runbook/adder-cpu-int8-inference-report.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import torch

from adder.data import (
    fixed_boundary_values,
    make_generator,
    sample_values,
    targets,
    to_matrix,
)
from adder.infer import (
    CpuAdder,
    export_int8,
    from_trained,
    load_int8,
    predict,
    quantize_static,
    save_int8,
)
from adder.model import AdderTransformer, load_checkpoint


@dataclass(frozen=True)
class DeployConfig:
    fp32_ckpt: str = "checkpoints/adder/adder-final.pt"
    out_dir: str = "checkpoints/adder-cpu-int8"
    calib_size: int = 65_536
    calib_seed: int = 2024
    test_size: int = 10_000
    test_seed: int = 12_345
    large_size: int = 100_000
    large_seed: int = 777
    threads: tuple[int, ...] = (1, 6)
    batches: tuple[int, ...] = (1, 16, 256, 4096)


@dataclass(frozen=True)
class Accuracy:
    samples: int
    digit_acc: float
    carry_acc: float
    sum_acc: float


def accuracy(
    predictor: Callable[[torch.Tensor], tuple[torch.Tensor, torch.Tensor]], values: torch.Tensor
) -> Accuracy:
    """逐位、进位与整和准确率。predictor 接收 [B,10,8] 矩阵，返回 argmax 数字与进位。"""
    n = values.shape[0]
    digit_ok = 0
    carry_ok = 0
    sum_ok = 0
    for start in range(0, n, 8192):
        mat = to_matrix(values[start : start + 8192])
        d_true, c_true = targets(mat)
        pd, pc = predictor(mat)
        d_eq = pd == d_true
        digit_ok += int(d_eq.sum())
        carry_ok += int((pc == c_true).sum())
        sum_ok += int(d_eq.all(dim=-1).sum())
    return Accuracy(
        samples=n,
        digit_acc=digit_ok / (n * 8),
        carry_acc=carry_ok / (n * 8),
        sum_acc=sum_ok / n,
    )


def _trained_predictor(
    model: AdderTransformer,
) -> Callable[[torch.Tensor], tuple[torch.Tensor, torch.Tensor]]:
    model.eval()

    def run(mat: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        with torch.inference_mode():
            out = model(mat)
        return out["digit_logits"].argmax(-1), out["carry_logits"].argmax(-1)

    return run


def _cpu_predictor(model: CpuAdder) -> Callable[[torch.Tensor], tuple[torch.Tensor, torch.Tensor]]:
    def run(mat: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return predict(model, mat)

    return run


_COMPILE = "compile"


def _compile(model: CpuAdder) -> Callable[[torch.Tensor], object]:
    # TODO(types): torch.compile 存根返回 partially unknown，显式收窄
    compile_fn = cast(Callable[..., Callable[[torch.Tensor], object]], getattr(torch, _COMPILE))
    return compile_fn(model, dynamic=False)


def time_fn(fn: Callable[[torch.Tensor], object], x: torch.Tensor, reps: int) -> float:
    """返回中位数延迟（毫秒）。"""
    with torch.inference_mode():
        for _ in range(5):
            fn(x)
        ts: list[float] = []
        for _ in range(reps):
            t0 = time.perf_counter()
            fn(x)
            ts.append(time.perf_counter() - t0)
    return statistics.median(ts) * 1e3


def _reps(batch: int) -> int:
    return {1: 300, 16: 200, 256: 60, 4096: 15}.get(batch, 20)


def run_benchmark(
    cfg: DeployConfig,
    trained: AdderTransformer,
    cpu32: CpuAdder,
    cpu8: CpuAdder,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    trained.eval()
    base_x = to_matrix(sample_values(max(cfg.batches), make_generator(31), boundary_frac=0.0))
    for threads in cfg.threads:
        torch.set_num_threads(threads)
        variants: dict[str, Callable[[torch.Tensor], object]] = {
            "fp32 训练图（nn.TransformerEncoder）": lambda x: trained(x),
            "fp32 CPU 推理图": lambda x: cpu32(x),
            "fp32 CPU 推理图 + torch.compile": _compile(cpu32),
            "int8 静态 W8A8（部署）": lambda x: cpu8(x),
        }
        for batch in cfg.batches:
            x = base_x[:batch]
            reps = _reps(batch)
            row: dict[str, object] = {"threads": threads, "batch": batch}
            for label, fn in variants.items():
                ms = time_fn(fn, x, reps)
                row[label] = {"latency_ms": ms, "sums_per_s": batch / (ms / 1e3)}
            rows.append(row)
            print(
                json.dumps({k: v for k, v in row.items()}, ensure_ascii=False, default=str),
                flush=True,
            )
    return rows


def build(cfg: DeployConfig) -> dict[str, Any]:
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    trained = load_checkpoint(Path(cfg.fp32_ckpt), device="cpu")
    cpu32 = from_trained(trained)
    calib = to_matrix(
        sample_values(cfg.calib_size, make_generator(cfg.calib_seed), boundary_frac=0.1)
    )
    cpu8 = quantize_static(cpu32, calib)

    int8_path = out / "adder-cpu-int8.pt"
    save_int8(export_int8(cpu8), int8_path)
    loaded = load_int8(int8_path)

    sets = {
        "test": sample_values(cfg.test_size, make_generator(cfg.test_seed), boundary_frac=0.0),
        "large": sample_values(cfg.large_size, make_generator(cfg.large_seed), boundary_frac=0.0),
        "boundary": fixed_boundary_values(),
    }
    predictors: dict[str, Callable[[torch.Tensor], tuple[torch.Tensor, torch.Tensor]]] = {
        "fp32 训练图": _trained_predictor(trained),
        "fp32 CPU 推理图": _cpu_predictor(cpu32),
        "int8 静态 W8A8（内存）": _cpu_predictor(cpu8),
        "int8 静态 W8A8（从文件加载）": _cpu_predictor(loaded),
    }
    acc: dict[str, dict[str, Accuracy]] = {}
    for label, pred in predictors.items():
        acc[label] = {k: accuracy(pred, v) for k, v in sets.items()}
        print(label, {k: round(v.sum_acc, 5) for k, v in acc[label].items()}, flush=True)

    probe = to_matrix(sets["large"][:4096])
    with torch.inference_mode():
        a_d, a_c = cpu8(probe)
        b_d, b_c = loaded(probe)
        load_diff = max(float((a_d - b_d).abs().max()), float((a_c - b_c).abs().max()))
        fp_d, _ = cpu32(probe)
        tr = trained(probe)
        fp_diff = float((fp_d - tr["digit_logits"]).abs().max())
    consistency = {
        "fp32_vs_trained_max_abs_logit_diff": fp_diff,
        "int8_file_vs_memory_max_abs_logit_diff": load_diff,
    }

    rows = run_benchmark(cfg, trained, cpu32, cpu8)

    summary: dict[str, Any] = {
        "date": date.today().isoformat(),
        "cpu": _cpu_name(),
        "torch": torch.__version__,
        "qengine": torch.backends.quantized.engine,
        "file_sizes": {
            "fp32_checkpoint_bytes": Path(cfg.fp32_ckpt).stat().st_size,
            "int8_artifact_bytes": int8_path.stat().st_size,
        },
        "accuracy": {label: {k: vars(v) for k, v in per.items()} for label, per in acc.items()},
        "consistency": consistency,
        "benchmark": rows,
    }
    (out / "deploy-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return summary


def _cpu_name() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


def render_report(cfg: DeployConfig, summary: dict[str, Any], report_path: Path) -> None:
    sizes: dict[str, int] = summary["file_sizes"]
    fp32_b = sizes["fp32_checkpoint_bytes"]
    int8_b = sizes["int8_artifact_bytes"]
    acc: dict[str, dict[str, dict[str, Any]]] = summary["accuracy"]
    rows: list[dict[str, Any]] = summary["benchmark"]
    cons: dict[str, float] = summary["consistency"]
    fp_diff = cons["fp32_vs_trained_max_abs_logit_diff"]
    load_diff = cons["int8_file_vs_memory_max_abs_logit_diff"]

    lines: list[str] = []
    lines.append("# 竖式加法模型 CPU int8 推理报告")
    lines.append("")
    lines.append(f"生成日期：{summary['date']}  ")
    lines.append(
        f"CPU：{summary['cpu']}；torch {summary['torch']}；量化后端 {summary['qengine']}  "
    )
    lines.append("对应规格：[[adder-cpu-int8-inference]]；决策：[[ADR-0004-cpu-int8-inference]]")
    lines.append("")
    lines.append("## 1. 操作步骤")
    lines.append("")
    lines.append("1. 确认 fp32 检查点存在：`backend/checkpoints/adder/adder-final.pt`。")
    lines.append("2. 在 backend/ 下执行（隐藏 GPU，确保 CPU 测量纯净）：")
    lines.append("   ```sh")
    lines.append("   CUDA_VISIBLE_DEVICES= uv run --group train python -m adder.cpu_deploy \\")
    lines.append(
        "       --report ../agent-knowledge/operations-runbook/adder-cpu-int8-inference-report.md"
    )
    lines.append("   ```")
    lines.append(
        "3. 脚本依次执行：加载 fp32 → 转换为 CPU 推理图 → 用 65,536 条训练分布样本校准激活范围 → "
        "静态量化 → 导出 `adder-cpu-int8.pt` → 从文件重新加载 → 三路精度评估 → 延迟/吞吐基准 → "
        "写出本报告与 `deploy-summary.json`。"
    )
    lines.append(
        "4. 验证：`uv run --group train pytest`、`uv run ruff check .`、"
        "`uv run --group train pyright`。"
    )
    lines.append("")
    lines.append("## 2. 量化方案")
    lines.append("")
    lines.append("| 项目 | 取值 |")
    lines.append("|---|---|")
    lines.append("| 方式 | 静态 PTQ：校准得到固定 scale，运行时无范围统计 |")
    lines.append(
        "| 线性层 | 全部 10 个 nn.Linear（qkv、out、FFN 两层、两个输出头）→ fbgemm int8 GEMM |"
    )
    lines.append(
        "| 权重 | int8 存储，每输出行对称 scale，取值限制在 [-64, 63]"
        "（fbgemm AVX2 饱和限制，见 ADR-0004） |"
    )
    lines.append("| 激活 | quint8 per-tensor 仿射，范围来自校准集 |")
    lines.append("| FFN | 第二层输入与第一层输出共用 quint8 参数，ReLU 直接在 quint8 上执行 |")
    lines.append("| 保持 fp32 | Embedding、LayerNorm、残差加法、softmax、注意力矩阵乘 |")
    lines.append("")
    lines.append("## 3. 文件体积")
    lines.append("")
    lines.append("| 文件 | 字节 | KiB |")
    lines.append("|---|---|---|")
    lines.append(f"| fp32 训练检查点 | {fp32_b:,} | {fp32_b / 1024:.1f} |")
    lines.append(f"| int8 部署文件 | {int8_b:,} | {int8_b / 1024:.1f} |")
    lines.append(f"| 比值 | | ×{fp32_b / int8_b:.2f} |")
    lines.append("")
    lines.append("## 4. 精度")
    lines.append("")
    lines.append("| 模型 | 数据集 | 样本数 | 逐位 | 进位 | 整和 |")
    lines.append("|---|---|---|---|---|---|")
    ds_names = [("test", "测试集"), ("large", "大样本"), ("boundary", "边界集")]
    for label, per in acc.items():
        for key, ds_label in ds_names:
            a = per[key]
            lines.append(
                f"| {label} | {ds_label} | {a['samples']} | {a['digit_acc'] * 100:.3f}% | "
                f"{a['carry_acc'] * 100:.3f}% | {a['sum_acc'] * 100:.2f}% |"
            )
    lines.append("")
    lines.append(
        f"一致性：fp32 CPU 推理图与训练图的最大 logit 差 {fp_diff:.2e}；"
        f"int8 内存模型与从文件加载模型的最大 logit 差 {load_diff:.2e}。"
    )
    lines.append("")
    lines.append("## 5. 推理速度（中位数延迟，越低越好；吞吐 = 整和/秒）")
    lines.append("")
    variant_labels = [
        "fp32 训练图（nn.TransformerEncoder）",
        "fp32 CPU 推理图",
        "fp32 CPU 推理图 + torch.compile",
        "int8 静态 W8A8（部署）",
    ]
    for threads in cfg.threads:
        lines.append(f"### {threads} 线程")
        lines.append("")
        header = "| batch | " + " | ".join(f"{v} 延迟 ms" for v in variant_labels)
        lines.append(header + " | int8 相对 fp32 CPU |")
        lines.append("|" + "---|" * (len(variant_labels) + 2))
        for row in rows:
            if row["threads"] != threads:
                continue
            cells = [f"{row[v]['latency_ms']:.3f}" for v in variant_labels]
            ratio = (
                row["fp32 CPU 推理图"]["latency_ms"] / row["int8 静态 W8A8（部署）"]["latency_ms"]
            )
            lines.append(f"| {row['batch']} | " + " | ".join(cells) + f" | ×{ratio:.2f} |")
        lines.append("")
    lines.append("## 6. 局限与未测项")
    lines.append("")
    lines.append(
        "- 测试机为 2016 年的 Broadwell Xeon（AVX2，无 VNNI）。"
        "在支持 VNNI/AMX 的 CPU 上 int8 的相对收益可能不同。"
    )
    lines.append("- 基准只测模型前向，不含调用方的 tree_sum、数据拼接与金额格式化。")
    lines.append(
        "- 小批量（batch=1）时延迟主要来自算子调度开销，int8 额外的量化/反量化算子会使其变慢。"
    )
    lines.append("- 整和准确率阈值 99.9% 仍为规格草案，需人类确认。")
    lines.append("")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="竖式加法模型 CPU int8 部署流水线")
    defaults = DeployConfig()
    parser.add_argument("--fp32-ckpt", default=defaults.fp32_ckpt)
    parser.add_argument("--out-dir", default=defaults.out_dir)
    parser.add_argument(
        "--report",
        default="../agent-knowledge/operations-runbook/adder-cpu-int8-inference-report.md",
    )
    args = parser.parse_args()
    cfg = DeployConfig(fp32_ckpt=args.fp32_ckpt, out_dir=args.out_dir)
    summary: dict[str, Any] = build(cfg)
    render_report(cfg, summary, Path(args.report))
    print(f"report written to {args.report}")


if __name__ == "__main__":
    main()
