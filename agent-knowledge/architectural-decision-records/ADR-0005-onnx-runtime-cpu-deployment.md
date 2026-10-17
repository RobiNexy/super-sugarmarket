# ADR-0005: 采用 ONNX Runtime fp32 作为 CPU 小批量推理部署路径

日期：2026-10-15 | 状态：Accepted（人类确认）| 取代：[[ADR-0004-cpu-int8-inference]] 的部署路径决定（静态 int8 不再是默认路径）| 被取代：无

## 背景

结账的 `tree_sum` 对每批 10 行调用一次模型，购物车的典型 batch 很小。实测（Xeon E5-1650 v4，Broadwell AVX2）：

- PyTorch fp32 CPU 图：batch 1 约 0.51 ms（1 线程）。
- PyTorch 静态 int8：batch 1 约 1.03 ms，比 fp32 慢。
- ONNX Runtime fp32：batch 1 约 0.13 ms（1 线程），最大 logit 差约 2e-5，整和准确率与 PyTorch 相同。
- ORT 静态 int8（QDQ）：准确率为 0%，原因未查明，且比 ORT fp32 慢。
- 6 线程大批量（4096）时 ORT fp32 慢于 PyTorch（85 ms 对 73 ms），但这不是本项目的主要场景。

人类确认主要关注小批量推理，并允许引入 ONNX Runtime。

## 决策

- 部署格式：ONNX（opset 17，batch 维动态）。
- 运行时：`onnxruntime` CPUExecutionProvider，fp32，图优化 ENABLE_ALL，默认单线程（intra_op=1）。
- 依赖：运行时新增 `onnxruntime`；train 组新增 `onnx`（用于导出与校验）。
- 推理封装做输入校验，非法输入不进入 ORT。
- int8 与 TensorRT 不作为本路径；TensorRT 仅 GPU，不适用于 CPU 目标。
- 静态 int8 代码（`adder/infer.py`）保留作为实验，不作为默认部署路径。

## 考虑过的方案

- PyTorch fp32 CPU 图（现状）：无新依赖，但小批量慢约 4 倍。
- PyTorch + torch.compile：小批量 0.33 ms，无新依赖；但编译耗时大，且运行时仍需 PyTorch。作为备选保留。
- PyTorch 静态 int8：小批量更慢，仅大批量有收益，否决为默认路径。
- ORT 静态 int8：准确率 0%，否决。
- TensorRT：仅 NVIDIA GPU，不满足 CPU 目标。
- OpenVINO：未测试，需要另行评估。

## 理由

- 小批量延迟是主要指标，ORT 在此最优（约 0.13 ms，相对 PyTorch 快约 3.5 倍）。
- 部署运行时不需要 PyTorch，依赖更轻（ORT wheel 约 20 MB）。
- 导出的 ONNX 可用 `onnx.checker` 检查，并可与训练图逐条比对。

## 后果

- 好处：小批量延迟显著降低；运行时依赖减少；路径可验证。
- 代价与风险：新增两个依赖；大批量吞吐低于 PyTorch 6 线程；ONNX 导出依赖 torch 导出器版本，升级需回归测试；ORT 版本需锁定在 uv.lock。
- 未决：是否需要 int8 或 TensorRT（GPU）以覆盖大批量场景。

## 触发重新评估的条件

- 结账切片的典型 batch 持续大于 256，且吞吐成为指标。
- ORT 与 PyTorch 输出出现不一致且无法修复。
- 人类要求 GPU 推理（TensorRT 或 PyTorch CUDA 可再评估）。

## 影响面

搜索 `[[ADR-0005-` 可得到引用此决策的规格与代码意图块。当前关联：[[adder-onnx-cpu-inference]]、[[adder-cpu-int8-inference]]。
