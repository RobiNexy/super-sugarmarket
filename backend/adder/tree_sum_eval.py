"""神经树形求和的端到端精度评估（真实 ONNX 模型，随机购物车）。

@purpose 统计 tree_sum 在不同购物车行数与行值分布下的精确命中率与误差，并生成运行手册报告。
@spec [[tree-sum-neural-addition]]
@invariants 随机种子固定；精确和由整数加法计算；报告数字全部由脚本计算。

用法（在 backend/ 下）：
    uv run --group train python -m adder.tree_sum_eval \\
        --report ../agent-knowledge/operations-runbook/tree-sum-accuracy-report.md
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from adder.onnx_runtime import OnnxAdder
from adder.tree_sum import MAX_ROW, tree_sum

CART_SIZES = (1, 2, 5, 10, 11, 30, 100)
CARTS_PER_SIZE = 2000
DISTRIBUTIONS: dict[str, tuple[int, int]] = {
    "均匀 0–9,999,999（训练分布）": (0, MAX_ROW),
    "小额 0–99,999（≤ ¥999.99 行）": (0, 99_999),
}


@dataclass(frozen=True)
class Stat:
    carts: int
    exact: float
    mean_abs_err: float
    max_abs_err: int
    mean_rel_err: float


def run_eval(
    adder: OnnxAdder, carts_per_size: int = CARTS_PER_SIZE, seed: int = 2026
) -> dict[str, dict[int, Stat]]:
    results: dict[str, dict[int, Stat]] = {}
    rng = np.random.default_rng(seed)
    for dist_name, (lo, hi) in DISTRIBUTIONS.items():
        per_size: dict[int, Stat] = {}
        for n in CART_SIZES:
            exact = 0
            abs_errs: list[int] = []
            rel_errs: list[float] = []
            for _ in range(carts_per_size):
                rows = rng.integers(lo, hi + 1, size=n, dtype=np.int64)
                truth = int(rows.sum())
                got = tree_sum(rows, adder)
                err = abs(got - truth)
                exact += int(err == 0)
                abs_errs.append(err)
                rel_errs.append(err / truth if truth else float(err))
            per_size[n] = Stat(
                carts=carts_per_size,
                exact=exact / carts_per_size,
                mean_abs_err=float(np.mean(abs_errs)),
                max_abs_err=int(np.max(abs_errs)),
                mean_rel_err=float(np.mean(rel_errs)),
            )
            print(f"{dist_name} n={n}: exact={per_size[n].exact:.4f}", flush=True)
        results[dist_name] = per_size
    return results


def render(results: dict[str, dict[int, Stat]], onnx_path: Path, report: Path) -> None:
    lines: list[str] = [
        "# 神经树形求和端到端精度报告",
        "",
        f"生成日期：{date.today().isoformat()}  ",
        f"模型：`{onnx_path}`（ONNX Runtime fp32，单线程）",
        "对应规格：[[tree-sum-neural-addition]]；"
        "推理后端：[[ADR-0005-onnx-runtime-cpu-deployment]]",
        "",
        "## 1. 操作步骤",
        "",
        "1. 确认 ONNX 模型存在：`backend/checkpoints/adder-onnx/adder.onnx`"
        "（由 `adder.onnx_export` 生成）。",
        "2. 在 backend/ 下执行：",
        "   ```sh",
        "   CUDA_VISIBLE_DEVICES= uv run --group train python -m adder.tree_sum_eval \\",
        "       --report ../agent-knowledge/operations-runbook/tree-sum-accuracy-report.md",
        "   ```",
        "3. 每个（行值分布，购物车行数）组合生成固定种子的随机购物车，比较 tree_sum 与整数精确和。",
        "",
        "## 2. 结果",
        "",
    ]
    for dist_name, per_size in results.items():
        lines.append(f"### {dist_name}")
        lines.append("")
        lines.append(
            "| 行数 | 购物车数 | 精确命中率 | 平均绝对误差 | 最大绝对误差 | 平均相对误差 |"
        )
        lines.append("|---|---|---|---|---|---|")
        for n, st in per_size.items():
            lines.append(
                f"| {n} | {st.carts} | {st.exact * 100:.2f}% | {st.mean_abs_err:,.1f} | "
                f"{st.max_abs_err:,} | {st.mean_rel_err * 100:.4f}% |"
            )
        lines.append("")
    lines += [
        "## 3. 解读",
        "",
        "- 精确命中率衡量整单金额（整数分）是否与精确和完全一致；"
        "只要有一个批次的数字错误，结果即不精确。",
        "- 误差随购物车行数增加：批次越多，误差累积的机会越多。",
        "- 本报告不包含结账层的差异诊断与免单规则（见 [[open-questions-awaiting-human]]）。",
        "",
        "## 4. 局限",
        "",
        "- 随机购物车的行值分布是假设；真实商品价格分布需另行统计后再评估。",
        "- 仅评估 fp32 ONNX 模型；int8 与其他推理后端不在本报告范围内。",
        "",
    ]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="神经树形求和端到端精度评估")
    parser.add_argument("--onnx", default="checkpoints/adder-onnx/adder.onnx")
    parser.add_argument(
        "--report",
        default="../agent-knowledge/operations-runbook/tree-sum-accuracy-report.md",
    )
    parser.add_argument("--carts", type=int, default=CARTS_PER_SIZE)
    args = parser.parse_args()
    onnx_path = Path(args.onnx)
    adder = OnnxAdder(onnx_path, threads=1)
    results: dict[str, Any] = run_eval(adder, carts_per_size=args.carts)
    render(results, onnx_path, Path(args.report))
    print(f"report written to {args.report}")


if __name__ == "__main__":
    main()
