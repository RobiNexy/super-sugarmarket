# 任务看板（最后更新：2026-10-14）

任务粒度以一次会话可完成的垂直切片为宜（约 30 分钟至 2 小时）；Ready 任务必须自包含；In Progress 最多 2 项；短期任务不编号；整理时清空 Done，git 历史负责归档。

## 当前目标

建立一个本机可运行的 Sugarmarket 展示商城，完成商品浏览、购物车、Transformer 结账计算、模拟下单，以及后台商品/库存管理和订单查看。技术栈决策见 [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]。

## In Progress（硬性上限 2 个）

- 暂无；当前会话完成冷启动知识库，尚未开始业务开发。

## Ready（已拆解，新会话可直接开工）

- 暂无；先取得模型设计文档与前端风格模板，并裁决 [[open-questions-awaiting-human]] 中影响规格的事项。

## Backlog（未拆解，只是念头）

- 接收并阅读人类提供的单 HTML 风格模板、Transformer 设计文档；据此建立首批商品浏览、结账计算、订单/库存规格和验收标准。
- 明确货币与金额精度、库存扣减与订单状态、后台访问控制等业务规则，更新 [[open-questions-awaiting-human]]。
- 重建约 100 种演示商品及所需图片/描述，确定可维护的种子数据来源与格式。
- 建立 React + TypeScript / FastAPI + Pydantic / SQLite 单仓库本机骨架，并配置 strict 类型检查、测试和 lint 三绿工具链。
- 实现并验收商品浏览、购物车、Transformer 结账计算、模拟订单创建及数据持久化的端到端流程。
- 实现首版后台：管理商品与库存、查看订单；按确认后的库存和订单规则编写规格与测试。

## Done（整理时清空；git 历史负责归档）

- [x] 安装 AI Native 工作流知识库并通过完整性校验。
- [x] 完成项目目的、范围与技术栈访谈，撰写首版知识库和 Accepted ADR-0001。
