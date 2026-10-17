# 竖式加法模型的 int8 权重量化与压缩报告

状态：Deprecated（被 [[adder-cpu-int8-inference]] 取代；保留为历史记录，其中的代码已删除）
最后更新：2026-10-15

## 背景与问题

> 注：本规格的“权重伪量化 + 反量化推理”方案不能加速推理，已由 [[adder-cpu-int8-inference]] 取代。

[[adder-transformer-column-addition-training]] 产出的 fp32 检查点约 432 KiB。结账切片若部署到小型本机服务或浏览器，需要更小的权重文件，同时不能明显损害整和准确率。本规格定义 8 bit 权重量化的范围、训练方法、验收标准与报告内容。

## 目标与非目标

### 目标

- 对全部 Linear、Embedding 与注意力 in_proj 权重做每输出行对称 int8 量化。
- 采用量化感知训练（QAT）：以 fp32 检查点为初始化，用伪量化前向与直通估计器微调。
- 导出可独立加载的 int8 文件（`backend/checkpoints/adder-int8/adder-int8.pt`），并提供加载函数。
- 与 fp32 模型、训练后量化（PTQ，无微调）基线对照，生成压缩报告。

### 非目标

- 不量化激活（W8A32）；不实现整数内核推理，不测量 int8 推理速度。
- 不量化偏置与 LayerNorm 参数。
- 不改变模型结构或数据生成。

## 用户与领域规则

- 量化只改变权重表示，不改变输入/输出协议（[[adder-transformer-column-addition-training]]）。
- 量化值域 [-127, 127]，不使用 -128，保证对称。
- 每个输出行的 scale 为 fp32；int8 文件保存 int8 值与 scale。

## 主流程

1. 加载 fp32 检查点，为目标权重挂载伪量化 parametrization。
2. 用与 fp32 训练相同的数据分布，以较小学习率微调固定步数（`adder.qat`）。
3. 去除 parametrization，取出 fp32 潜变量权重，逐张量量化为 int8 + scale，写入 `adder-int8.pt`。
4. 对三路模型（fp32、PTQ int8、QAT int8）评估同一批数据并写报告。
5. 一致性检查：伪量化模型与导出 int8 模型对同一输入的 logits 差异应低于 1e-4。

## 边界与失败场景

| 场景 | 预期行为 |
|---|---|
| 全零行权重 | scale 取下限，量化结果为 0，不产生 NaN |
| 导出文件格式版本不匹配 | 加载时报错，不静默使用 |
| 伪量化前向绕过 parametrization（例如 transformer 快速路径） | 单元测试失败 |
| QAT 后精度低于 fp32 阈值 | 报告中明确标注，不隐藏结果 |

## 验收标准

- [x] Given 任意 2 维权重，When 每行对称量化，Then 量化值在 [-127,127] 且反量化误差不超过半个 scale。
- [x] Given 伪量化模型与其导出的 int8 文件，When 同一输入前向，Then 两者 logits 一致（误差 < 1e-4）。
- [x] Given 导出文件，When 检查张量，Then 12 个量化张量为 int8，偏置与 LayerNorm 为 fp32。
- [x] Given QAT int8 模型，When 在 1 万测试集评估，Then 整和准确率 ≥ 99.9%（实测 99.97%，与 fp32 持平，见报告）。
- [x] Given 压缩报告，When 生成，Then 包含操作步骤、压缩比、三路精度对照与局限说明。

每条验收标准至少映射一个测试；测试文件意图块用 `@spec [[adder-int8-quantization]]` 回链。

## 数据与接口

- 数据模型：无数据库。
- API 契约：无。
- 代码入口：已删除（原 `backend/adder/quant.py`、`backend/adder/qat.py`，2026-10-15 撤销）。本条目仅作历史记录。
- 报告：`operations-runbook/adder-int8-compression-report.md`（由脚本生成）。

## 依赖与影响面

- ADR：[[ADR-0003-int8-weight-qat]]
- 受影响能力：未来结账切片的模型加载方式。
- 依赖：[[adder-training-environment-setup]]

## 未决问题

- 无。W8A8 与 int8 路径已由 [[adder-cpu-int8-inference]] 与 ADR-0005 处理，本条目不再推进。
