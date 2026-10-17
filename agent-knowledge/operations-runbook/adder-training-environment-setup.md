# 竖式加法模型训练环境搭建（本机 RTX 2080 Ti）

适用环境：Ubuntu 24.04.5 LTS（kernel 7.0.0-38-generic），NVIDIA RTX 2080 Ti（22 GB 显存，compute capability 7.5），NVIDIA 驱动 595.99.02（nvidia-smi 报告 CUDA 13.2）
最后验证：2026-10-14

## 目的与影响

在本机搭建 PyTorch CUDA 训练环境，用于训练 `human_files/adder_transformer.md` 中的竖式列加法 Transformer（规格见 [[adder-transformer-column-addition-training]]）。
训练依赖位于 `backend/pyproject.toml` 的 `train` 依赖组，不影响 API 运行环境（`uv sync` 默认不安装 torch）。

## 版本清单

| 组件 | 版本 | 来源 |
|---|---|---|
| 系统 Python | 3.12.3 | Ubuntu 自带 `/usr/bin/python3.12` |
| uv | 0.10.11 | `~/.local/bin/uv` |
| PyTorch | 2.11.0+cu128 | `https://download.pytorch.org/whl/cu128` |
| CUDA 运行时（随 wheel 分发） | 12.8 | PyTorch wheel 自带 nvidia-*-cu12 包 |
| cuDNN | 9.19.0.56 | PyPI（由 torch 依赖带入） |
| NumPy | 2.5.2 | PyPI |
| 系统 `nvcc` | 未安装 | 不需要：PyTorch wheel 自带运行时 |

驱动 595 向下兼容 CUDA 12.8 运行时；不需要安装 CUDA Toolkit。

## 前置条件

- `nvidia-smi` 能看到 RTX 2080 Ti。
- 已安装 uv。
- 磁盘剩余空间约 10 GB（CUDA 相关 wheel 较大）。

## 操作步骤

1. 确认 GPU 与驱动：
   ```sh
   nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
   ```
2. 在 `backend/pyproject.toml` 中已配置：
   - 依赖组 `train`：`torch>=2.9,<3`、`numpy>=2,<3`；
   - 专用索引 `pytorch-cu128`（`explicit = true`），并通过 `[tool.uv.sources]` 只把 torch 指向该索引。
3. 锁定并安装训练依赖：
   ```sh
   cd backend
   uv lock
   uv sync --group train
   ```
4. 验证 GPU 可用：
   ```sh
   uv run --group train python -c "import torch;print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
   ```
   期望输出包含 `True` 与 `NVIDIA GeForce RTX 2080 Ti`。
5. 运行训练相关测试（CPU 测试，仍需 train 组）：
   ```sh
   uv run --group train pytest
   ```
6. 启动正式训练（建议后台运行，见排障）：
   ```sh
   uv run --group train python -m adder.train --steps 100000 --device cuda --out-dir checkpoints/adder
   ```

## 验证与成功标准

- `torch.cuda.is_available()` 为 `True`，设备 capability 为 `(7, 5)`。
- 2 层 Transformer 前向在 GPU 上执行无错误。
- 实测 fp16 4096×4096 矩阵乘约 17.8 TFLOPS（参考值，非基准测试）。
- 训练日志每 500 步输出 JSON 行，每 5000 步评估测试集；结束后生成 `checkpoints/adder/adder-final.pt` 与 `report.json`。
- 2026-10-14 正式运行（10 万步，约 25 分钟）：测试集整和 99.97%，边界集 10/10。
- 训练已结束（2026-10-16，Q-010）。部署使用导出的 ONNX 模型，导出命令见 [[adder-onnx-cpu-inference-report]]：`uv run --group train python -m adder.onnx_export --ckpt checkpoints/adder/adder-final.pt --out checkpoints/adder-onnx/adder.onnx`。

## 回滚/恢复

- 移除训练组：删除 `backend/.venv` 中的 torch 相关包，或 `uv sync`（不带 `--group train`）；并不影响 `pyproject.toml` 中其他依赖。
- 检查点与报告位于 `backend/checkpoints/`（已被 `.gitignore` 忽略），可直接删除重训。

## 排障

| 症状 | 可能原因 | 处理方式 |
|---|---|---|
| 首次 CUDA 调用报 `CUDA-capable device(s) is/are busy or unavailable` | 首次初始化时 GPU 被其他进程（桌面合成器等）占用的瞬时状态 | 重跑一次；本机第二次即成功，未复现 |
| 通过 Agent/远程 shell 启动的训练被中止后进程消失（约 6.4 万步时发生） | 中止命令时进程组被一并结束；`setsid nohup` 也未能保护 | 训练应在独立终端（tmux/screen）中运行；训练脚本暂无断点续训，中断需从头重跑 |
| `torch.cuda.is_available()` 为 False | 误装了 CPU 版 wheel 或索引未生效 | 确认 `uv sync --group train` 中 `torch` 版本带 `+cu128` 后缀 |
| pyright 对 torch 报 `partially unknown` | torch 2.11 类型存根不完整 | 在对应行使用 `# pyright: ignore[reportUnknownMemberType]` 并附 TODO(types) 理由 |

## 相关文档

- [[adder-transformer-column-addition-training]]
- [[ADR-0002-pytorch-local-cuda-training]]
