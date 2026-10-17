"""竖式列加法样本与真值的单元测试。

@purpose 验证输入约束、进位真值与边界样本与整数加法一致。
@spec [[adder-transformer-column-addition-training]]
@covers adder/data.py 的 to_matrix、check_matrix、targets、sample_values、fixed_boundary_values
"""

from __future__ import annotations

from typing import cast

import pytest
import torch

from adder.data import (
    COLS,
    MAX_ROW_VALUE,
    ROWS,
    check_matrix,
    fixed_boundary_values,
    make_generator,
    sample_values,
    targets,
    to_matrix,
)


def _rows(t: torch.Tensor) -> list[list[int]]:
    return cast(list[list[int]], t.tolist())  # pyright: ignore[reportUnknownMemberType]  # TODO(types): torch 2.11 存根不完整，上游问题


def _decimal_digits(n: int) -> list[int]:
    return [(n // 10**i) % 10 for i in range(COLS)]


def _carries_from_sum(rows: list[int]) -> list[int]:
    # 第 i 列向上进位 c_{i+1} = floor(低 i+1 位列之和 / 10^(i+1))，
    # 其中低位列之和 = sum_r (v_r mod 10^(i+1))。
    out: list[int] = []
    for i in range(COLS):
        mod = 10 ** (i + 1)
        out.append(sum(r % mod for r in rows) // mod)
    return out


def test_targets_match_integer_addition_on_random_rows() -> None:
    gen = make_generator(7)
    values = sample_values(512, gen, boundary_frac=0.2)
    digits, carries = targets(to_matrix(values))
    for b in range(values.shape[0]):
        rows = _rows(values[b : b + 1])[0]
        total = sum(rows)
        assert _rows(digits[b : b + 1])[0] == _decimal_digits(total)
        assert _rows(carries[b : b + 1])[0] == _carries_from_sum(rows)


def test_all_nines_column_sums_produce_full_carry_chain() -> None:
    rows = [MAX_ROW_VALUE] * ROWS
    digits, carries = targets(to_matrix(torch.tensor([rows])))
    assert _rows(digits[0:1])[0] == _decimal_digits(sum(rows)) == [0, 9, 9, 9, 9, 9, 9, 9]
    assert carries[0, COLS - 1].item() == 0


def test_sample_values_respects_row_and_value_bounds() -> None:
    gen = make_generator(3)
    values = sample_values(2048, gen, boundary_frac=0.3)
    assert values.shape == (2048, ROWS)
    assert int(values.min()) >= 0
    assert int(values.max()) <= MAX_ROW_VALUE
    nonzero_rows = (values != 0).sum(dim=1)
    assert int(nonzero_rows.max()) <= ROWS


def test_to_matrix_rejects_out_of_range_row() -> None:
    with pytest.raises(ValueError):
        to_matrix(torch.tensor([[MAX_ROW_VALUE + 1] + [0] * (ROWS - 1)]))


def test_check_matrix_rejects_nonzero_most_significant_column() -> None:
    matrix = torch.zeros(1, ROWS, COLS, dtype=torch.int64)
    matrix[0, 0, COLS - 1] = 1
    with pytest.raises(ValueError):
        check_matrix(matrix)


def test_fixed_boundary_set_includes_ten_max_rows_without_overflow() -> None:
    values = fixed_boundary_values()
    full_max = [row for row in _rows(values) if row == [MAX_ROW_VALUE] * ROWS]
    assert len(full_max) == 1
    digits, carries = targets(to_matrix(values))
    assert digits.shape == (values.shape[0], COLS)
    assert int(carries[:, -1].abs().sum()) == 0


def test_boundary_sampling_covers_column_sum_ninety() -> None:
    # 全部 10 行同为 9_999_999（或 9）时，每列数字和为 90，是唯一的最大列和类别
    gen = make_generator(11)
    values = sample_values(512, gen, boundary_frac=1.0)
    full_block = [
        row for row in _rows(values) if len(set(row)) == 1 and row[0] in (9, MAX_ROW_VALUE)
    ]
    assert len(full_block) > 0
    matrix = to_matrix(values)
    col_sums = matrix.sum(dim=1)
    assert int(col_sums.max()) == 90
