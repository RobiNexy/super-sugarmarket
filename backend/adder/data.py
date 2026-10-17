"""竖式列加法样本生成与精确真值计算。

@purpose 生成 10x8 竖式矩阵样本，并用整数逐列进位推导数字与进位监督真值。
@spec [[adder-transformer-column-addition-training]]
@invariants 最高列恒为 0；每行值在 [0, 9_999_999]；行数在 [1, 10]；真值与 Python 整数加法一致。
@touches 被 backend/adder/train.py 与 backend/adder/model.py 的测试共同使用。
"""

from __future__ import annotations

import torch

ROWS = 10
COLS = 8
MAX_ROW_VALUE = 9_999_999
MAX_VALID_ROWS = 10
SUM_CLASSES = 91  # 列和取值 0..90（10 行 * 9）

_POW10 = torch.tensor([10**i for i in range(COLS)], dtype=torch.int64)
_BOUNDARY_VALUES = torch.tensor([0, 1, 9, MAX_ROW_VALUE], dtype=torch.int64)


def make_generator(seed: int) -> torch.Generator:
    gen = torch.Generator()
    gen.manual_seed(seed)
    return gen


def seed_everything(seed: int) -> None:
    torch.manual_seed(seed)  # pyright: ignore[reportUnknownMemberType]  # TODO(types): torch 存根不完整，上游问题


def to_matrix(values: torch.Tensor) -> torch.Tensor:
    """把 [B, 10] 整数行转为 [B, 10, 8] 数字矩阵（最低有效位在前）。

    要求 values 中每行在 [0, MAX_ROW_VALUE]，否则抛出 ValueError。
    """
    if values.shape[-1] != ROWS:
        raise ValueError(f"expected {ROWS} rows, got {values.shape[-1]}")
    if bool((values < 0).any()) or bool((values > MAX_ROW_VALUE).any()):
        raise ValueError("row value out of range [0, 9999999]")
    pow10 = _POW10.to(values.device)
    return (values.unsqueeze(-1) // pow10) % 10


def check_matrix(matrix: torch.Tensor) -> None:
    """校验 [B, 10, 8] 矩阵满足输入约束（数字 0..9，最高列为 0）。"""
    if matrix.shape[-2:] != (ROWS, COLS):
        raise ValueError(f"expected shape [*, {ROWS}, {COLS}], got {tuple(matrix.shape)}")
    if bool((matrix < 0).any()) or bool((matrix > 9).any()):
        raise ValueError("digit out of range 0..9")
    if bool((matrix[..., COLS - 1] != 0).any()):
        raise ValueError("most significant column must be all zero")


def targets(matrix: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """由矩阵计算逐列真值。

    返回 (digits, carries)：
    - digits[b, i] = 和的第 i 位（最低位在前）；
    - carries[b, i] = 第 i 列向第 i+1 列的进位（最高列为 0）。
    """
    check_matrix(matrix)
    sigma = matrix.sum(dim=1)  # [B, 8]
    carry = torch.zeros(sigma.shape[0], dtype=torch.int64, device=matrix.device)
    digit_cols: list[torch.Tensor] = []
    carry_cols: list[torch.Tensor] = []
    for i in range(COLS):
        t = carry + sigma[:, i]
        digit_cols.append(t % 10)
        carry = t // 10
        carry_cols.append(carry)
    digits = torch.stack(digit_cols, dim=1)
    carries = torch.stack(carry_cols, dim=1)
    if bool((carries[:, COLS - 1] != 0).any()):
        raise AssertionError("final carry must be zero for constrained inputs")
    return digits, carries


def sample_values(
    batch: int,
    generator: torch.Generator,
    *,
    boundary_frac: float = 0.1,
) -> torch.Tensor:
    """生成 [B, 10] 随机行值。

    每个样本有 1..10 个有效行，其余行补零。boundary_frac 比例的样本为边界样本，
    其中一半为“整块同值”（10 行均取 {0, 1, 9, 9_999_999} 之一，列和可达 90），
    另一半为逐行从 {0, 1, 9, 9_999_999} 中取值且倾向于取满 10 行。
    整块同值样本对应设计文档 §6.2 的“多行全 9”边界，覆盖列和 90 这一罕见类别。
    """
    rows = torch.randint(
        0, MAX_ROW_VALUE + 1, (batch, ROWS), generator=generator, dtype=torch.int64
    )
    count = torch.randint(1, MAX_VALID_ROWS + 1, (batch,), generator=generator, dtype=torch.int64)

    is_boundary = torch.rand(batch, generator=generator) < boundary_frac
    n_b = int(is_boundary.sum().item())
    if n_b > 0:
        per_row = _BOUNDARY_VALUES[
            torch.randint(0, _BOUNDARY_VALUES.numel(), (n_b, ROWS), generator=generator)
        ]
        uniform = (
            _BOUNDARY_VALUES[
                torch.randint(0, _BOUNDARY_VALUES.numel(), (n_b,), generator=generator)
            ]
            .unsqueeze(1)
            .expand(n_b, ROWS)
        )
        block = torch.rand(n_b, generator=generator) < 0.5
        boundary_rows = torch.where(block.unsqueeze(1), uniform, per_row)
        full = torch.rand(n_b, generator=generator) < 0.5
        boundary_count = torch.where(
            block | full,
            torch.full((n_b,), MAX_VALID_ROWS, dtype=torch.int64),
            count[is_boundary],
        )
        rows[is_boundary] = boundary_rows
        count[is_boundary] = boundary_count

    valid = torch.arange(ROWS).unsqueeze(0) < count.unsqueeze(1)
    return torch.where(valid, rows, torch.zeros_like(rows))


def fixed_boundary_values() -> torch.Tensor:
    """确定性的边界样本集（[N, 10]）。"""
    m = MAX_ROW_VALUE
    cases: list[list[int]] = [
        [0] * ROWS,
        [1] + [0] * (ROWS - 1),
        [m] + [0] * (ROWS - 1),
        [m] * ROWS,
        [m] * 9 + [0],
        [1] * ROWS,
        [9] * ROWS,
        [m, 1] + [0] * (ROWS - 2),
        [9, 90, 900, 9_000, 90_000, 900_000, 9_000_000, 0, 0, 0],
        [5_000_000, 5_000_000] + [0] * (ROWS - 2),
    ]
    return torch.tensor(cases, dtype=torch.int64)
