# SugarMarket

本机/局域网运行的网上小卖部演示项目。顾客浏览 100 种 Emoji 商品、用购物袋下单，成交金额由一个竖式列加法 Transformer（ONNX Runtime CPU 推理）计算，老板在无认证的后台送货完成后扣减库存。

## 背景

这个项目是对大学课程设计半成品的重制。原作者的话：

> 我有一个大学时候，做课程设计的半成品项目。SugarMarket，那是我们一组人培训Django做的课设，灵感来源就是我们当时住的酒店叫苏格公寓，下面有个无人小卖部。我们做了个网站。能在线购物，并且结账。那时候才大一，我们啥也不会，勉强跑起来，直到最后还有个问题没解决，购物车算不了帐，于是我们写死成15块钱，演示的时候就刚好凑15块钱走完流程，顺利过关。算不了帐的原因是我们未能理解Javascript，或者说那时候我们压根不会做开发。现在有技术了，有时间了想重做它，来纪念我们的青春。用神经网络计算加法也是为了恶搞，杀鸡用牛刀。

这次用 FastAPI + React 重写。当年算不了的账，这次真的交给了神经网络来算。

## 功能

- **商品目录**：饮品、零食、速食泡面、日用品四个分类，桌面每行 5 张商品卡，支持组合 Emoji 插画（变形、叠放、裁切合成的整体图案）。
- **购物袋与结账**：购物袋保存在浏览器 localStorage；结账只需房间号，无注册无登录。下单时库存不足按可售数量截断，无货商品自动跳过。
- **神经结账**：订单金额完全来自模型输出；与精确加法差异超出 ±20% 时显示“嘿嘿，神经网络有时候就是很神经 🤪”，模型返回 null 或推理异常时免单（“神（经网络）赐予你免单”）。
- **老板后台**：无凭据校验（输入任意密码即可进入），查看/完成订单并原子扣减库存，维护商品与组合 Emoji 图层。入口为 `/#admin`。
- **订单数据**：SQLite `orders` / `order_items` 表，待送货订单预占库存，老板完成订单时才真正扣减。

## 环境

- Python 3.12（由 [uv](https://docs.astral.sh/uv/) 管理依赖）
- Node.js 22 与 npm（构建/开发前端用）

## 本地开发

安装依赖：

```sh
cd backend
uv sync            # 运行依赖；训练组 train 需另行 --group train
cd ../frontend
npm ci
```

终端一启动 API（首次启动创建 SQLite 数据库并增量导入种子商品）：

```sh
cd backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

终端二启动前端；Vite 会把 `/api` 请求代理给本机 API：

```sh
cd frontend
npm run dev
```

打开 <http://127.0.0.1:5173/> 即顾客页面，<http://127.0.0.1:5173/#admin> 为老板后台。

神经加法器模型 `backend/checkpoints/adder-onnx/adder.onnx` 随仓库分发；若缺失，结账会按设计创建免单订单而不是报错。

## 验证

```sh
cd frontend
npm run typecheck
npm test
npm run lint
npm run build

cd ../backend
uv run pytest
uv run ruff check .
uv run pyright
```

## 部署

面向店内局域网的单机部署（systemd + Caddy），含备份与升级流程，见
`agent-knowledge/operations-runbook/deployment-tutorial.md` 与
`agent-knowledge/operations-runbook/deployment-overview.md`。

注意：后台没有认证，不要把服务发布到公网。

## 数据

- 数据库 `backend/data/sugarmarket.sqlite3` **随仓库分发**（这是刻意的：大学时期的数据就因为没提交而全部丢失）。可用环境变量 `SUGARMARKET_DB_PATH` 把运行时数据库指到其他位置；本地开发产生的改动会体现为 Git 工作区变更。
- 商品种子数据在 `backend/app/data/products.json`，启动时只补入缺失的商品 ID，不覆盖老板的修改。

## 项目结构

```
backend/
  adder/        # 竖式列加法 Transformer：训练、ONNX 导出、推理、tree_sum
  app/          # FastAPI：商品目录、结账、订单、后台
  tests/        # pytest（76 项）
frontend/
  src/          # React 顾客页与老板后台（Vitest 16 项）
agent-knowledge/  # 设计规格、ADR、运行手册（AI 协作知识库）
```
