# ADR-0004: 采用静态 W8A8 + fbgemm 的 CPU int8 推理，取代权重伪量化方案

日期：2026-10-15 | 状态：Superseded（部署路径由 [[ADR-0005-onnx-runtime-cpu-deployment]] 取代；静态 int8 代码保留为实验，不作为默认路径） | 取代：[[ADR-0003-int8-weight-qat]] | 被取代：[[ADR-0005-onnx-runtime-cpu-deployment]]

## 背景

人类要求量化的目标是 CPU 上的推理加速。ADR-0003 的方案只量化权重并在加载时反量化为 fp32，文件更小，但推理没有变快，不满足目标。

在 Intel Xeon E5-1650 v4（Broadwell，AVX2，无 VNNI）上的实测结论：

- PyTorch 动态量化（`quantize_dynamic`）比 fp32 更慢，因为每次调用都要统计激活范围。
- 直接使用 fbgemm 的 8 bit 权重与 8 bit 激活会在 AVX2 上饱和（uint8×int8 成对求和溢出 int16），误差约 1.0；把权重限制到 [-64, 63] 后误差降到约 0.06，精度恢复。
- 静态 int8（预打包权重 + 校准得到的固定激活参数）在较宽的线性层上比 fp32 快；FFN 中 ReLU 在 quint8 上执行、避免一次反量化与重新量化后，整体比 fp32 快约 1.26–1.29 倍（批量 4096）。
- 小批量（batch 1、16）时量化/反量化算子的开销大于收益，int8 比 fp32 慢。
- `torch.compile` 对 fp32 图有效（batch 1 约 0.33 ms），但对含量化算子的图效果不稳定。

## 决策

- 推理图改为显式的 CPU 图（`adder.infer.CpuAdder`），所有矩阵乘为 `nn.Linear`；与训练图在 fp32 下等价。
- 量化方式：静态 PTQ。激活范围由 65,536 条训练分布样本校准；权重每输出行对称量化，取值限制在 [-64, 63]。
- 运行时使用 `torch.ops.quantized.linear`（fbgemm）；非线性运算保持 fp32。
- 部署文件格式 `adder-cpu-int8-v1`，保存 int8 权重、scale、bias 与激活参数。
- 不引入 ONNX Runtime、OpenVINO 等新依赖；若需要，另行提交人类批准。
- 不采用 QAT：静态 PTQ 已满足精度门槛（测试集整和 99.96%，fp32 为 99.97%）。
- 推荐用法（原）：大批量吞吐使用 int8；单条或小批量延迟敏感场景使用 fp32 + `torch.compile`。该推荐已被 ADR-0005 取代：默认部署路径为 ONNX Runtime fp32，`torch.compile` 仅作备选，int8 仅为实验。

## 考虑过的方案

- 权重伪量化后反量化为 fp32（ADR-0003）：压缩有效，不加速，已取代。
- `torch.ao.quantization.quantize_dynamic`：实测比 fp32 慢（0.59–0.95 倍），否决。
- 静态 int8 + 8 bit 权重：fbgemm 饱和，误差约 1.0，否决。
- ONNX Runtime 的 int8 路径：可能更快，但需要新依赖，需人类批准后再评估。
- 全程 int8 流水线（LayerNorm、残差在量化域执行）：收益有限且实现复杂，暂不采用。

## 理由

- 静态量化把范围统计从运行时移到离线校准，消除动态量化的主要开销。
- 7 bit 有效权重是 fbgemm 在 AVX2 上的已知限制，不会改变存储格式，只改变取值范围。
- 只依赖 PyTorch 已有组件，部署与训练环境一致。

## 后果

- 好处：大批量（4096）吞吐在 6 线程下比 fp32 CPU 图高约 29%，文件比 fp32 检查点小约 3 倍（146 KiB 对 432 KiB），精度与 fp32 持平。
- 代价与风险：小批量比 fp32 慢；性能只在 Broadwell AVX2 上测量；依赖 `torch._make_per_channel_quantized_tensor` 等私有 API 构造量化权重，升级 torch 时需要回归测试。
- 已裁决（2026-10-16，Q-010）：小批量不采用 int8 或 torch.compile 作为默认路径，统一由 ADR-0005 的 ORT fp32 承担。

## 触发重新评估的条件

- 结账切片的典型批量持续小于 256，且延迟是主要指标。
- 部署机器支持 VNNI 或 AMX。
- torch 升级后私有量化 API 不可用或结果变化。
- 人类批准引入 ONNX Runtime 或其他推理引擎。

## 影响面

搜索 `[[ADR-0004-` 可得到引用此决策的规格与代码意图块。当前关联：[[adder-cpu-int8-inference]]、[[adder-int8-quantization]]（已弃用）。
