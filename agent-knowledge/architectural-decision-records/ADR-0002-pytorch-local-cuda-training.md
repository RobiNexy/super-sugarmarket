# ADR-0002: 采用 PyTorch（CUDA 12.8 wheel）在本机 RTX 2080 Ti 上训练竖式加法 Transformer

日期：2026-10-14 | 状态：Accepted（2026-10-16，人类确认；模型训练已结束，见 Q-010）| 取代：无 | 被取代：无

## 背景

ADR-0001 将 Transformer 框架与训练硬件列为“尚未决定”。人类已提供竖式列加法模型设计文档（`human_files/adder_transformer.md`），并明确本机硬件为 RTX 2080 Ti（22 GB）、要求自行搭建训练环境。模型极小（\(d=64\)，2 层，列长 8），瓶颈在于迭代次数与实验效率而非多卡扩展。

## 决策

- 训练框架：**PyTorch 2.11.0**，使用官方 `cu128` wheel，内置 CUDA 12.8 运行时；不要求系统安装 CUDA Toolkit 或 `nvcc`。
- 训练位置：本机 GPU，不接入任何云服务或付费资源。
- 依赖隔离：torch 与 numpy 置于 `backend/pyproject.toml` 的 `train` 依赖组，API 运行环境不安装。
- 环境配置与复现步骤记录于 [[adder-training-environment-setup]]。

## 考虑过的方案

- PyTorch（CUDA wheel，本方案）。
- JAX / Flax：生态对本设计无明显优势，团队熟悉度不明。
- TensorFlow：不再是本项目首选。
- 纯 CPU 训练：模型小，但 10^5 步的迭代在 CPU 上耗时显著更长。
- 系统级 CUDA Toolkit + 源码编译 PyTorch：维护成本高，本机不需要。

## 理由

- PyTorch 的 `nn.TransformerEncoder` 与自定义损失可直接映射设计文档中的因果 mask 与双头 CE 损失。
- 官方 wheel 自带运行时，避免系统 CUDA 版本与驱动之间的耦合。
- 驱动 595 向下兼容 CUDA 12.8 运行时；2080 Ti（sm_75）在 wheel 的架构列表中。
- 训练依赖隔离保证 FastAPI 运行环境保持轻量。

## 后果

- 好处：环境可复现（uv.lock 锁定）；训练 1e5 步约需 30 分钟（实测前 3 万步节奏）。
- 代价与风险：torch 依赖体积大（约数 GB）；torch 2.11 类型存根对部分成员为 partially unknown，需要 pyright ignore 注释；2080 Ti 无 bf16，本次训练使用 fp32。
- 训练已结束：正式检查点为 `backend/checkpoints/adder/adder-final.pt`（10 万步，fp32）。部署不依赖本训练环境，见 [[ADR-0005-onnx-runtime-cpu-deployment]]。
- 未决：是否在后续切片改用 fp16 AMP 以加速（需另行验证精度）。当前无继续训练计划，此项暂不推进。

## 触发重新评估的条件

- 训练需要多卡或超出 22 GB 显存的模型。
- torch 对 sm_75 的支持在后续 wheel 中被移除。
- 人类要求改用其他框架或在线训练服务。

## 影响面

搜索 `[[ADR-0002-` 可得到引用此决策的规格与代码意图块。当前关联：[[adder-transformer-column-addition-training]]、[[adder-training-environment-setup]]、[[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]。
