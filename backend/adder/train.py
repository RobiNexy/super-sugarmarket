"""竖式列加法模型的训练与离线评估入口。

@purpose 按设计文档训练 AdderTransformer，输出检查点与测试/边界集指标。
@spec [[adder-transformer-column-addition-training]]
@invariants 真值由整数加法计算；评估集与训练流使用不同随机种子；检查点不入库。

用法（在 backend/ 下）：
    uv run --group train python -m adder.train --steps 100000 --device cuda
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import torch

from adder.data import (
    COLS,
    fixed_boundary_values,
    make_generator,
    sample_values,
    seed_everything,
    targets,
    to_matrix,
)
from adder.model import AdderTransformer, ModelConfig, adder_loss, save_checkpoint


@dataclass(frozen=True)
class TrainConfig:
    steps: int = 100_000
    batch_size: int = 256
    lr: float = 3e-4
    carry_weight: float = 1.0
    boundary_frac: float = 0.1
    seed: int = 0
    eval_size: int = 10_000
    eval_seed: int = 12_345
    eval_every: int = 5_000
    log_every: int = 500
    device: str = "cpu"
    out_dir: str = "checkpoints/adder"


@dataclass(frozen=True)
class EvalMetrics:
    samples: int
    digit_acc: float
    carry_acc: float
    sum_acc: float


def evaluate(model: AdderTransformer, values: torch.Tensor, device: torch.device) -> EvalMetrics:
    """对 [N, 10] 行值计算逐位、进位与整和准确率。"""
    model.eval()
    digit_ok = 0
    carry_ok = 0
    sum_ok = 0
    total = values.shape[0]
    with torch.inference_mode():
        for start in range(0, total, 4096):
            chunk = values[start : start + 4096]
            matrix = to_matrix(chunk)
            digits, carries = targets(matrix)
            out = model(matrix.to(device))
            pred_d = out["digit_logits"].argmax(dim=-1).cpu()
            pred_c = out["carry_logits"].argmax(dim=-1).cpu()
            d_eq = pred_d == digits
            c_eq = pred_c == carries
            digit_ok += int(d_eq.sum().item())
            carry_ok += int(c_eq.sum().item())
            sum_ok += int(d_eq.all(dim=-1).sum().item())
    cells = total * COLS
    return EvalMetrics(
        samples=total,
        digit_acc=digit_ok / cells,
        carry_acc=carry_ok / cells,
        sum_acc=sum_ok / total,
    )


def train(cfg: TrainConfig, model_cfg: ModelConfig | None = None) -> dict[str, object]:
    device = torch.device(cfg.device)
    seed_everything(cfg.seed)
    gen = make_generator(cfg.seed)

    model = AdderTransformer(model_cfg).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.lr)

    eval_gen = make_generator(cfg.eval_seed)
    eval_values = sample_values(cfg.eval_size, eval_gen, boundary_frac=0.0)
    boundary_values = fixed_boundary_values()

    history: list[dict[str, float]] = []
    t0 = time.time()
    run_loss = 0.0
    run_n = 0
    for step in range(1, cfg.steps + 1):
        model.train()
        values = sample_values(cfg.batch_size, gen, boundary_frac=cfg.boundary_frac)
        matrix = to_matrix(values)
        digits, carries = targets(matrix)
        out = model(matrix.to(device))
        loss, d_loss, c_loss = adder_loss(
            out, digits.to(device), carries.to(device), cfg.carry_weight
        )
        optimizer.zero_grad(set_to_none=True)
        loss.backward()  # pyright: ignore[reportUnknownMemberType]  # TODO(types): torch 2.11 存根不完整，上游问题
        optimizer.step()  # pyright: ignore[reportUnknownMemberType]  # TODO(types): torch 2.11 存根不完整，上游问题
        run_loss += float(loss.item())
        run_n += 1

        if step % cfg.log_every == 0:
            entry = {
                "step": float(step),
                "loss": run_loss / run_n,
                "digit_loss": float(d_loss.item()),
                "carry_loss": float(c_loss.item()),
                "elapsed_s": time.time() - t0,
            }
            history.append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
            run_loss = 0.0
            run_n = 0

        if step % cfg.eval_every == 0 or step == cfg.steps:
            m = evaluate(model, eval_values, device)
            print(f"[eval step {step}] test {asdict(m)}", flush=True)
            save_checkpoint(model, Path(cfg.out_dir) / "adder-latest.pt")

    final_test = evaluate(model, eval_values, device)
    final_boundary = evaluate(model, boundary_values, device)
    out_dir = Path(cfg.out_dir)
    ckpt_path = out_dir / "adder-final.pt"
    save_checkpoint(model, ckpt_path)
    report: dict[str, object] = {
        "config": asdict(cfg),
        "model_config": asdict(model.config),
        "test": asdict(final_test),
        "boundary": asdict(final_boundary),
        "checkpoint": str(ckpt_path),
        "train_seconds": time.time() - t0,
        "history": history,
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="训练竖式列加法 Transformer")
    defaults = TrainConfig()
    parser.add_argument("--steps", type=int, default=defaults.steps)
    parser.add_argument("--batch-size", type=int, default=defaults.batch_size)
    parser.add_argument("--lr", type=float, default=defaults.lr)
    parser.add_argument("--carry-weight", type=float, default=defaults.carry_weight)
    parser.add_argument("--boundary-frac", type=float, default=defaults.boundary_frac)
    parser.add_argument("--seed", type=int, default=defaults.seed)
    parser.add_argument("--eval-every", type=int, default=defaults.eval_every)
    parser.add_argument("--log-every", type=int, default=defaults.log_every)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--out-dir", default=defaults.out_dir)
    args = parser.parse_args()

    cfg = TrainConfig(
        steps=args.steps,
        batch_size=args.batch_size,
        lr=args.lr,
        carry_weight=args.carry_weight,
        boundary_frac=args.boundary_frac,
        seed=args.seed,
        eval_every=args.eval_every,
        log_every=args.log_every,
        device=args.device,
        out_dir=args.out_dir,
    )
    report = train(cfg)
    print("FINAL test", report["test"])
    print("FINAL boundary", report["boundary"])


if __name__ == "__main__":
    main()
