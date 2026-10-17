# ADR-0003: 采用每行对称 int8 权重量化与 QAT 压缩竖式加法模型

日期：2026-10-15 | 状态：Superseded | 取代：无 | 被取代：[[ADR-0004-cpu-int8-inference]]（推理加速目标未满足，权重反量化方案不加速）

## 背景

[[ADR-0002-pytorch-local-cuda-training]] 确定了本机 PyTorch 训练环境。加法器模型训练完成后（[[adder-transformer-column-addition-training]]），人类要求量化为 8 bit 并输出压缩报告。模型较小，主要目标是减小权重体积并保持精度，而不是实现整数推理加速。

## 决策

- 量化位宽：权重 int8，对称，值域 [-127, 127]。
- 粒度：每输出行一个 fp32 scale。
- 范围：Linear、Embedding、注意力 in_proj 权重；偏置与 LayerNorm 保持 fp32；激活保持 fp32（W8A32）。
- 方法：量化感知训练，以 fp32 检查点初始化，伪量化用 `torch.nn.utils.parametrize` 挂载，梯度用直通估计器。
- 运行时：导出的 int8 文件在加载时反量化为 fp32 矩阵进行计算。

## 考虑过的方案

- 训练后量化（PTQ）：无需训练，但精度风险需要先验证；保留为对照基线。
- W8A8 量化：需要替换 `nn.TransformerEncoder` 为自定义块，以便在注意力与 FFN 前插入激活量化；成本高，暂不采用。
- PyTorch 内置 eager 量化流程（`torch.ao.quantization`）：对 Embedding 与 MultiheadAttention 的支持不完整，且需要 CPU 后端，故不采用。
- fp16 半精度：压缩比只有 2 倍，不满足本次 8 bit 要求。

## 理由

- 每行 scale 对输出通道的量化误差最小，实现简单，且与权重矩阵布局匹配。
- parametrization 不改变模型类，保持 `state_dict` 键名与 fp32 一致，便于 PTQ 与 QAT 对照。
- W8A32 已覆盖体积目标；激活量化的收益需要先测量，因此放到后续决策。

## 后果

- 好处：权重体积约为 fp32 的四分之一（不含 scale 与文件开销）；导出与加载流程可独立复现。
- 代价与风险：不产生推理加速；加载时仍使用 fp32 计算；需要在报告中说明精度差距。
- 已取代，不再推进 W8A8；真实 int8 实验与部署路径见 [[ADR-0004-cpu-int8-inference]] 与 [[ADR-0005-onnx-runtime-cpu-deployment]]。

## 触发重新评估的条件

- 结账切片需要真实 int8 推理速度或内存上限。
- QAT int8 精度低于人类确认的阈值。
- 人类要求改为 W4 或混合精度。

## 影响面

搜索 `[[ADR-0003-` 可得到引用此决策的规格与代码意图块。当前关联：[[adder-int8-quantization]]。
