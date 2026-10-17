# 竖式加法模型的 CPU int8 推理

状态：Draft（部署路径已由 [[adder-onnx-cpu-inference]] 取代；本规格的 int8 实现保留为实验）
最后更新：2026-10-15

## 背景与问题

[[adder-transformer-column-addition-training]] 的模型只有 fp32 检查点，推理依赖 PyTorch 训练图（`nn.TransformerEncoder`）。结账切片需要在本机 CPU 上批量计算竖式加法，目标是降低延迟、提高吞吐。之前的“权重量化后反量化为 fp32 计算”不能加速推理，已被本规格取代（见 [[adder-int8-quantization]]）。

## 目标与非目标

### 目标

- 提供不依赖训练图的 CPU 推理模型，fp32 结果与训练图一致（logit 误差 < 1e-4）。
- 提供真 int8 推理：线性层使用 int8 GEMM（fbgemm），激活为静态 quint8，无运行时范围统计。
- int8 精度不低于 fp32 的 99.9% 门槛（测试集整和），边界集全部正确。
- 导出为单个 int8 部署文件，可在无训练代码的环境加载。
- 以同一批数据、同一硬件测量精度与延迟/吞吐，并如实记录结果。

### 非目标

- 不做 W8A8 量化感知训练：静态 PTQ 的校准结果已满足精度门槛；若精度不足再重新评估。
- 不引入 ONNX Runtime、OpenVINO 等新依赖（需人类批准，见 [[ADR-0004-cpu-int8-inference]]）。
- 不改变 tree_sum、金额格式化或结账接口。

## 用户与领域规则

- 输入矩阵与训练模型相同：`[B, 10, 8]`，数字 0..9，最高列为 0。
- 线性层权重限制在 [-64, 63]，以避开 fbgemm AVX2 的 int16 饱和（与 torch 的 reduce_range 一致）。
- FFN 第二层输入与第一层输出共用 quint8 参数，ReLU 在量化域执行。
- 校准数据为训练分布（65,536 条，种子 2024），与评估集（种子 12345、777）独立。

## 主流程

1. 加载 fp32 检查点，转换为 CPU 推理图（`adder.infer.from_trained`）。
2. 用校准集记录每个线性层输入/输出范围，静态量化（`adder.infer.quantize_static`）。
3. 导出 `adder-cpu-int8.pt`（格式 `adder-cpu-int8-v1`），并从文件重新加载。
4. 在测试集、大样本、边界集上评估：fp32 训练图、fp32 CPU 图、int8（内存）、int8（文件）。
5. 在 1 与 6 线程、batch 1/16/256/4096 下测量中位延迟，报告见 `operations-runbook/adder-cpu-int8-inference-report.md`。

## 边界与失败场景

| 场景 | 预期行为 |
|---|---|
| 加载的文件格式不是 `adder-cpu-int8-v1` | 抛出 ValueError，不静默加载 |
| 输入形状不是 `[B, 10, 8]` | 抛出 ValueError |
| 校准范围外的激活 | quint8 饱和，精度下降；报告中体现 |
| 未经 `quantize_static` 的模型导出 | 抛出 ValueError |
| 批量为 1 | 结果正确；延迟可能高于 fp32（量化算子开销） |

## 验收标准

- [x] Given 随机初始化模型，When 转换为 CPU 推理图，Then logits 与训练图误差 < 1e-4。
- [x] Given 任意线性层，When 静态量化，Then 权重整数值位于 [-64, 63]，且输出与 fp32 的相对误差 < 5%。
- [x] Given 量化后的 FFN，When 检查参数，Then lin2 输入参数与 lin1 输出参数逐一相等。
- [x] Given 导出文件，When 重新加载，Then 输出与内存模型逐位相等。
- [x] Given 错误格式文件，When 加载，Then 报错。
- [x] Given 训练检查点，When 在 1 万测试集上评估 int8 模型，Then 整和准确率 ≥ 99.9%（实测 99.96%）。
- [x] Given 边界集，When 评估 int8 模型，Then 全部正确。
- [ ] Given int8 部署模型，When 在 4096 批量上与 fp32 CPU 图比较，Then 延迟更低（实测 6 线程 ×1.29，1 线程 ×1.26）。已满足；int8 不作为默认部署路径（ADR-0005），仅保留为实验。
- [x] Given 部署需求，When 给出单条推理的低延迟路径，Then int8 不作为小批量首选。已裁决：默认路径为 ORT fp32（[[ADR-0005-onnx-runtime-cpu-deployment]]），torch.compile 不采用（Q-010）。

每条验收标准至少映射一个测试或基准输出；测试文件意图块用 `@spec [[adder-cpu-int8-inference]]` 回链。

## 数据与接口

- 部署文件：`backend/checkpoints/adder-cpu-int8/adder-cpu-int8.pt`（已被 `.gitignore` 忽略）。
- 代码入口：`backend/adder/infer.py`（推理图与量化）、`backend/adder/cpu_deploy.py`（流水线与报告）。
- Python 接口：`load_int8(path) -> CpuAdder`；`predict(model, matrix) -> (digits, carries)`。

## 依赖与影响面

- ADR：[[ADR-0004-cpu-int8-inference]]（取代 [[ADR-0003-int8-weight-qat]]）
- 依赖：[[adder-transformer-column-addition-training]]、[[adder-training-environment-setup]]
- 报告：`operations-runbook/adder-cpu-int8-inference-report.md`（由脚本生成）

## 未决问题

- 无。99.9% 阈值与 torch.compile 路径已由 Q-010 关闭；int8 不作为默认路径（ADR-0005）。
- 状态保持 Draft 仅表示 int8 实现为实验，不再推进为默认部署。
