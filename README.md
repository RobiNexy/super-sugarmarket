# SugarMarket

本机运行的网上小卖部演示项目。当前切片提供 SQLite 商品目录 API 和 React 商品浏览/分类筛选页面。

## 环境

- Node.js 22（可用 nvm 管理）与 npm
- Python 3.12（可用 uv 管理）

## 安装依赖

```sh
cd backend
uv sync
cd ../frontend
npm ci
```

## 本机运行

终端一启动 API（首次启动会创建 SQLite 数据库并装入 20 个模板演示商品）：

```sh
cd backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

终端二启动前端；Vite 会把 `/api` 请求代理给本机 API：

```sh
cd frontend
npm run dev
```

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

本地 SQLite 文件位于 `backend/data/sugarmarket.sqlite3`，不提交到 Git。更多项目上下文见 [[AI-AGENT-START-HERE]]。
