# 竖式加法模型的 ONNX Runtime CPU 小批量推理

状态：Done（人类于 2026-10-15 确认采用 ONNX Runtime fp32；2026-10-16 确认模型训练结束，99.9% 阈值通过，见 Q-010）
最后更新：2026-10-16

## 背景与问题

结账时 `tree_sum` 每次调用模型处理 10 行，典型购物车的单次调用 batch 很小（1 到数个）。
对小批量，当前 PyTorch 推理的单次延迟约为 0.5 ms（1 线程）。目标是降低这一延迟，并让运行时不依赖 PyTorch。
实测见 [[adder-cpu-int8-inference]] 与 [[ADR-0004-cpu-int8-inference]]：静态 int8 在小批量比 fp32 更慢，因此不作为默认路径。

## 目标与非目标

### 目标

- 导出为 ONNX（动态 batch 维），通过 `onnx.checker` 校验。
- 使用 ONNX Runtime（fp32，CPUExecutionProvider）推理，图优化级别为 ENABLE_ALL。
- 小批量（batch 1–16）延迟显著低于当前 PyTorch CPU 图；与训练图的 argmax 结果逐条一致。
- 推理封装对输入做运行时校验（形状、数字范围、最高列为 0），非法输入直接拒绝。
- 会话复用，线程数可配置，默认单线程（小批量最优）。

### 非目标

- 不做 int8（ORT 静态 int8 在本项目的测试中准确率为 0，原因未查明，本规格不依赖它）。
- 不做 TensorRT（仅 NVIDIA GPU）。
- 不改变模型结构或金额语义；tree_sum 与金额格式化仍在 Python 层。

## 用户与领域规则

- 输入与训练模型相同：`[B, 10, 8]`，取值 0..9，最高列为 0；B ≥ 1。
- 输出为两组 logits（数字 `[B,8,10]`、进位 `[B,8,10]`），由调用方取 argmax。
- 运行时只依赖 `onnxruntime` 与 `numpy`，不依赖 PyTorch。

## 主流程

1. `adder.onnx_export`：加载 fp32 最终检查点 `backend/checkpoints/adder/adder-final.pt`，导出 ONNX（opset 17，batch 动态），保存到 `backend/checkpoints/adder-onnx/adder.onnx`（当前文件 453,367 字节，442.7 KiB）。
2. 校验：`onnx.checker`；与 PyTorch 训练图在 20,000 条随机样本上 argmax 逐条一致，logit 最大差 < 1e-4。
3. `adder.onnx_runtime.OnnxAdder`：创建会话（一次），`predict(matrix)` 校验输入后返回 (数字, 进位) 的 argmax。
4. 基准：batch 1/2/4/16 下对比 PyTorch 训练图、PyTorch CPU 图、ORT，报告见 `operations-runbook/adder-onnx-cpu-inference-report.md`。

## 边界与失败场景

| 场景 | 预期行为 |
|---|---|
| 形状不是 `[B, 10, 8]` 或 B = 0 | 抛出 ValueError |
| 数字超出 0..9 或最高列非 0 | 抛出 ValueError，不进入 ORT |
| ONNX 文件缺失或损坏 | 构造时抛出错误，不静默回退 |
| 输入 dtype 非整数 | 转换前检查，非整数拒绝 |
| 多线程配置 | 默认 intra_op=1；可配置，报告记录效果 |

## 验收标准

- [x] Given 训练检查点，When 导出 ONNX，Then `onnx.checker` 通过，且 batch 维可变（测试 B=1、2、7、33）。
- [x] Given 20,000 条随机矩阵，When 比较 ORT 与 PyTorch 训练图，Then 数字与进位 argmax 全部一致，logit 最大差 < 1e-4（实测 100% 一致，最大差 1.9e-5）。
- [x] Given 非法输入（形状错误、数字越界、最高列非零），When 调用 predict，Then 抛出 ValueError。
- [x] Given 边界集，When 推理，Then 整和全部正确。
- [x] Given 测试集 1 万条，When 推理，Then 整和准确率 ≥ 99.9%（实测 99.96%；阈值经 Q-010 确认）。
- [x] Given 小批量 batch=1，When 基准（1 线程），Then 中位延迟低于 PyTorch CPU 图（实测 0.19 ms 对 0.60 ms，报告见 operations-runbook）。

每条验收标准至少映射一个测试或基准输出；测试文件意图块用 `@spec [[adder-onnx-cpu-inference]]` 回链。

## 数据与接口

- 导出文件：`backend/checkpoints/adder-onnx/adder.onnx`（`.gitignore` 已覆盖 `backend/checkpoints/`）。
- 代码入口：`backend/adder/onnx_export.py`、`backend/adder/onnx_runtime.py`。
- Python 接口：`OnnxAdder(path, threads=1).predict(matrix) -> (digits, carries)`。

## 依赖与影响面

- ADR：[[ADR-0005-onnx-runtime-cpu-deployment]]（部分取代 [[ADR-0004-cpu-int8-inference]] 的部署路径决定）
- 依赖：[[adder-transformer-column-addition-training]]（最终检查点，训练已结束）、[[adder-training-environment-setup]]
- 新依赖：`onnxruntime`（运行时）、`onnx`（train 组）。
- 结账层调用：[[tree-sum-neural-addition]] 通过 `OnnxAdder.predict` 使用本模型。

## 未决问题

- 是否需要 ORT 的进一步优化（如 I/O binding）：取决于调用方是否成为瓶颈，暂不推进。
