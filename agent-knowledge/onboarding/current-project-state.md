# 项目当前状态（最后更新：2026-10-14）

## 一句话状态

刚初始化，未开始业务开发；项目目的、首版范围和技术栈已经由人类确认并记录。

## 已完成并稳定运行的能力

- 暂无业务能力。

## 正在进行中的工作

- 暂无；后续候选任务见 [[task-board]]。

## 最近关键变更（最多保留 5 条，新内容置顶）

- 完成冷启动访谈，记录 Sugarmarket 的目标受众、首版场景/范围和技术栈决策 ADR-0001。
- 首版定义为本机演示：商品浏览、购物车、Transformer 结账计算、模拟订单，以及后台商品/库存管理和订单查看。
- 安装 AI Native 工作流知识库并通过 20/20 文件完整性校验。

## 已知问题与技术债

- 原课程设计商品数据库遗失，约 100 种演示商品需要重建。
- Transformer 模型设计文档和前端单 HTML 风格模板由人类后续提供。
- 金额精度、库存扣减与订单状态、后台访问控制等业务规则尚待确认，见 [[open-questions-awaiting-human]]。
- strict 类型检查、测试、lint 工具链尚未配置；在业务实现前按 [[task-board]] 处理。

## 环境

- 本地开发：React + TypeScript；FastAPI + Pydantic；SQLite；Transformer。开发者电脑已有 nvm 和 uv，具体版本与其他工具尚未配置。详见 [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]。
- 部署：首版仅本机运行；不要求线上部署。
