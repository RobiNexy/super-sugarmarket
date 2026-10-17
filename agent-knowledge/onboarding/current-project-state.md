# 项目当前状态（最后更新：2026-10-17）

## 一句话状态

首版商城全流程已实现：100 种商品目录、localStorage 购物袋、房间号结账、Transformer/`tree_sum` 成交金额、库存预占、订单落库，以及老板后台完成订单扣库存和商品维护。商品组合 Emoji 可编辑为变形、折叠、叠放的整体插画。

## 已完成并稳定运行的能力

- FastAPI `GET /api/products` 返回 100 种活动商品、元字符串价格、可售库存与组合 Emoji 描述。
- React 商品目录支持分类筛选、库存售罄禁用、组合 Emoji 整体画布及糖果色视觉。
- localStorage 保存购物袋；顾客用房间号结账，前端不计算总金额。
- `POST /api/checkout` 将商品单价按购买数量展开为整数分加数列表，经 ONNX Runtime fp32 `tree_sum` 归并；成交金额采用模型结果。
- 结账时 SQLite `BEGIN IMMEDIATE` 计算可售库存并创建订单；不足量按可售数量截断，无货商品跳过，全无货时拒绝下单。待送货订单预占库存，不在下单时扣减。
- 第二档（差异超 ±20%）、对照为零专用标签、第三档免单及库存提示已接入订单结果页。
- 后台提供提示密码的演示登录、待送货/已完成订单查询、完成订单原子扣库存、商品增改、Emoji 图层编辑和实时预览。
- 商品目录 100 种：饮品 25、零食 35、泡面速食 20、日用品 20；启动增量导入缺失种子，不覆盖已有商品的维护值。
- Transformer 最终检查点 `backend/checkpoints/adder/adder-final.pt`；部署模型 `backend/checkpoints/adder-onnx/adder.onnx`，ORT fp32，单线程。训练已结束。
- `tree_sum` 已实现并接受当前整单精度（训练分布 100 行 97.75%，小额 100 行 94.30%）。

## 正在进行中的工作

- 暂无；后续可选优化见 [[task-board]]。

## 最近关键变更（最多保留 5 条，新内容置顶）

- 按顾客视觉反馈重做商品页：饮品默认、分类专属 Emoji、速食泡面显示名、全部随机混排、桌面五列；增加红色悬浮购物袋/飞入动效、背景涂鸦和随机歪斜贴纸。
- 实现购物袋、结账 API、订单数据表、库存预占与订单价格档位；加入后台订单处理、商品 CRUD 和组合 Emoji 图层编辑器。
- 将种子商品增至 100 种；`products` 数据库按缺失 ID 增量补种，保留已有商品编辑。
- 商品目录 API 改为返回元字符串、可售库存和解码后的 `emoji_art`；前端根据服务器价格字符串展示。
- 2026-10-17 补充 Emoji 组合整体插画设计（Q-013），并实现固定画布、图层变形/折叠/裁切/叠放及后台编辑预览。
- 结账/后台/订单/API 规格与实现同步；Q-008 至 Q-013 记录裁决；ADR-0002 Accepted、ADR-0004 Superseded、ADR-0005 为 ONNX Runtime fp32 部署决策。

## 已知问题与技术债

- 检查点及 ONNX 文件在 `.gitignore` 中，不随 Git 仓库分发；当前开发机已有 ONNX 文件。若在无模型文件的机器上运行，推理加载失败会依既定规则创建免单订单。
- 检查点不纳入 Git；训练脚本暂无断点续训，但模型已停止训练，不再推进。
- int8 部署实验依赖 torch 私有 API；不影响默认 ONNX Runtime 路径。
- ONNX 导出使用 legacy TorchScript 导出器，PyTorch 会给出弃用提示；当前模型和推理路径可正常工作。
- 可选推理优化及管理操作日志暂不在首版范围。

## 环境

- 本地开发：Node.js 22/npm + React/TypeScript/Vite；Python 3.12/uv + FastAPI/Pydantic/Uvicorn；SQLite。
- 模型运行：ONNX Runtime + NumPy；不需要在 API 运行时加载 PyTorch。
- 训练环境：PyTorch 2.11+cu128，RTX 2080 Ti；训练结束。
- 部署：首版面向店内局域网单机部署（Linux + systemd + Caddy），后台无认证，不做公网发布。文档见 [[deployment-overview]] 与 [[deployment-tutorial]]。
