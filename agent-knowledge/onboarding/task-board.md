# 任务看板（最后更新：2026-10-17）

任务粒度以一次会话可完成的垂直切片为宜（约 30 分钟至 2 小时）；Ready 任务必须自包含；In Progress 最多 2 项；短期任务不编号；整理时清空 Done，git 历史负责归档。

## 当前目标

建立一个本机可运行的 Sugarmarket 展示商城：顾客浏览商品、购物袋结账，订单由老板送货后在后台完成并扣库存。商品目录、结账、订单后台、商品维护和 Emoji 整体插画编辑已实现。规格入口：[[checkout-cart-and-order]]、[[admin-backoffice]]、[[cute-ui-copy-and-motion]]、[[storefront-product-catalog-browsing-and-category-filter]]。

## In Progress（硬性上限 2 个）

- 暂无。

## Ready（已拆解，新会话可直接开工）

- 暂无首版阻塞切片。

## Backlog（未拆解）

- 可选优化：减少 `validate_matrix` 的 0.05 ms 开销；评估 ORT I/O binding。
- 可选优化：增补管理员操作日志或后台筛选；当前不在首版范围。

## Done（整理时清空；git 历史负责归档）

- [x] **切片一：购物车、结账与订单**：SQLite `orders`/`order_items`，`POST /api/checkout`，待送货订单预占库存，数量不足按可售量截断，无货商品跳过；所有无货时拒绝下单；Transformer/`tree_sum` 成交金额与结账档位；浏览器 localStorage 购物袋和房间号结账 UI。
- [x] **切片二：老板后台**：无凭据校验的可爱登录页、订单查询/确认送达/原子扣库存、商品新增编辑、组合 Emoji 图层编辑器与即时预览。
- [x] **切片三：商品目录扩充**：演示商品 100 种（饮品 25、零食 35、泡面速食 20、日用品 20），由缺失种子增量补入，不覆盖老板修改过的数据。
- [x] 组合 Emoji 作为整体插画：固定画布、图层变形/折叠/遮罩裁切/叠放；数据库/API 描述与商品卡/后台编辑器支持（Q-013）。
- [x] 结账档位（Q-008）、对照为零专用标签（Q-011）、tree_sum 当前精度接受（Q-009）、训练结束及 ONNX 部署（Q-010）。
- [x] ADR-0002 Accepted、ADR-0004 Superseded；部署默认 ONNX Runtime fp32（ADR-0005）。
- [x] AI Native 工作流知识库、首版商品目录及 React/FastAPI/SQLite 工具链。

## 验收记录

- 后端：`uv run pytest` 76 passed；`uv run ruff check .`、`uv run pyright` 全通过。
- 前端：`npm run typecheck`、`npm run lint`、`npm test`（15 passed）、`npm run build` 全通过。
- 提交策略：按神经加法器、商城结账/后台与商品目录切片分别提交（人类要求拆分提交）。
