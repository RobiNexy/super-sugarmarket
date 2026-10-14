# 项目当前状态（最后更新：2026-10-14）

## 一句话状态

商品目录首个全栈切片已实现并通过验证；购物车、Transformer 结账、订单和后台尚未实现。

## 已完成并稳定运行的能力

- FastAPI `GET /api/products` 从 SQLite 返回通过 Pydantic 校验的可展示商品。
- React/TypeScript 商品页展示 Emoji 商品卡、人民币两位小数价格、分类筛选及加载/空/错误状态。
- 首次数据库初始化会载入 20 种风格模板演示商品。

## 正在进行中的工作

- 暂无；后续候选任务见 [[task-board]]。

## 最近关键变更（最多保留 5 条，新内容置顶）

- 实现商品浏览全栈切片：SQLite 商品表/种子数据、FastAPI 目录 API、React 分类筛选与糖果色商品卡。
- 配置 npm/uv 工具链，TypeScript/Python strict 检查、前后端测试和 lint 全部通过。
- Transformer 输出是最终成交价；对照差异超出 ±50% 时提示，返回 null 时免单；普通加法不回退或拦截。
- 人类进一步确认金额使用人民币两位小数/内部整数分、老板送货后手动完成订单并扣库存、应用内不退货、后台无认证、商品使用 Emoji 而非真实图片。
- 已读取 `human_files/adder_transformer.md` 和 `human_files/template.html`；前者规定整数分、乘法展开与固定矩阵加法设计，后者提供糖果色/蜡笔风格及 Emoji 视觉参考。
- 完成冷启动访谈，记录 Sugarmarket 的目标受众、首版场景/范围和技术栈决策 ADR-0001。

## 已知问题与技术债

- 当前只有 20 种模板演示商品；目录需要扩充并完善至约 100 种商品。
- 购物车、Transformer 模型训练/推理接入、结账、订单履约和后台尚未实现；Transformer 框架及训练硬件尚未选定。

## 环境

- 本地开发：Node.js 22/npm + React/TypeScript/Vite；Python 3.12/uv + FastAPI/Pydantic/Uvicorn；SQLite。类型检查、测试、lint 工具已配置。详见 [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]。
- 部署：首版仅本机运行；不要求线上部署。
