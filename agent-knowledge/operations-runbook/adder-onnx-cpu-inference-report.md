# 竖式加法模型 ONNX Runtime 小批量推理报告

生成日期：2026-10-15<br>
CPU：Intel(R) Xeon(R) CPU E5-1650 v4 @ 3.60GHz；torch 2.11.0+cu128<br>
对应规格：[[adder-onnx-cpu-inference]]；决策：[[ADR-0005-onnx-runtime-cpu-deployment]]

## 1. 操作步骤

1. 确认检查点存在：`backend/checkpoints/adder/adder-final.pt`。
2. 导出并校验 ONNX（在 backend/ 下）：
   ```sh
   uv run --group train python -m adder.onnx_export --ckpt checkpoints/adder/adder-final.pt --out checkpoints/adder-onnx/adder.onnx
   ```
3. 运行小批量基准（隐藏 GPU 以保证 CPU 测量纯净）：
   ```sh
   CUDA_VISIBLE_DEVICES= uv run --group train python -m adder.onnx_bench \
       --report ../agent-knowledge/operations-runbook/adder-onnx-cpu-inference-report.md
   ```
4. 验证：`uv run --group train pytest`、`uv run ruff check .`、`uv run --group train pyright`。

## 2. 文件

- 检查点：`checkpoints/adder/adder-final.pt`
- ONNX 模型：`checkpoints/adder-onnx/adder.onnx`，大小 442.7 KiB

## 3. 中位延迟（ms，越低越好）

### 1 线程

| 路径 | batch 1 | batch 2 | batch 4 | batch 16 | batch 256 |
|---|---|---|---|---|---|
| PyTorch 训练图 | 0.5926 | 0.6287 | 0.6892 | 1.1623 | 9.1124 |
| PyTorch CPU 推理图 | 0.5981 | 0.6428 | 0.7141 | 1.1934 | 13.6486 |
| PyTorch CPU 推理图 + torch.compile | 0.3756 | 0.3589 | 0.4157 | 0.8336 | 8.1983 |
| ORT 封装 predict（含校验） | 0.1878 | 0.2244 | 0.3097 | 0.8224 | 10.8387 |
| ORT 原始 session.run（无校验） | 0.1387 | 0.1804 | 0.2643 | 0.7643 | 10.6570 |

相对 PyTorch CPU 推理图（同线程）：batch 1 ×3.18，batch 2 ×2.86，batch 4 ×2.31，batch 16 ×1.45，batch 256 ×1.26。

### 6 线程

| 路径 | batch 1 | batch 2 | batch 4 | batch 16 | batch 256 |
|---|---|---|---|---|---|
| PyTorch 训练图 | 0.5839 | 0.6580 | 0.7065 | 0.9402 | 3.0311 |
| PyTorch CPU 推理图 | 0.6353 | 0.6705 | 0.7212 | 0.9910 | 3.7021 |
| PyTorch CPU 推理图 + torch.compile | 0.3579 | 0.3684 | 0.4132 | 1.1137 | 3.6593 |
| ORT 封装 predict（含校验） | 0.1984 | 0.2302 | 0.3178 | 0.6683 | 5.5932 |
| ORT 原始 session.run（无校验） | 0.1639 | 0.1926 | 0.2754 | 0.6103 | 5.4334 |

相对 PyTorch CPU 推理图（同线程）：batch 1 ×3.20，batch 2 ×2.91，batch 4 ×2.27，batch 16 ×1.48，batch 256 ×0.66。

## 4. 局限与未测项

- 测量的是模型前向（含或不含封装校验），不含 tree_sum、金额格式化与 HTTP 开销。
- 测试机为 Broadwell Xeon（AVX2）；其他 CPU 的相对结果可能不同。
- 精度见 `adder/onnx_export.py` 的校验输出与测试；ONNX 与训练图的 argmax 一致性由导出时校验。
- 导出使用 PyTorch 的 TorchScript 导出器（`dynamo=False`），PyTorch 新版本已将其标记为弃用，升级时需回归。
