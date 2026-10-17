# Sugarmarket 部署文档

适用环境：Linux 服务器（Ubuntu 22.04/24.04 或 Debian 12），单机，单店。
最后更新：2026-10-17
操作步骤见 [[deployment-tutorial]]。

## 1. 目标与范围

- 把顾客商城与老板后台部署到店内/楼内局域网的一台机器上，供顾客扫码或输入地址访问。
- 不做公网发布。后台没有认证（见 [[admin-backoffice]]、Q-003），任何能访问后台地址的人都能改库存、完成订单。
- 不做多实例、高可用、备份集群。数据是一个 SQLite 文件。

## 2. 架构

```
浏览器 ──HTTP:80──▶ Caddy（或 nginx）
                      ├── /api/*     ──反向代理──▶ uvicorn 127.0.0.1:8000（FastAPI，单 worker）
                      │                               ├── SQLite 文件（SUGARMARKET_DB_PATH）
                      │                               └── ONNX 模型 backend/checkpoints/adder-onnx/adder.onnx
                      └── 其他路径    ──静态文件──▶ /srv/sugarmarket（前端 dist 构建产物）
```

| 组件 | 版本/来源 | 说明 |
|---|---|---|
| Python | 3.12（由 uv 管理） | 依赖见 `backend/pyproject.toml`，版本锁定在 `uv.lock` |
| FastAPI + uvicorn | `fastapi>=0.115`、`uvicorn>=0.34` | 运行 `app.main:app` |
| onnxruntime | `>=1.29.0`，CPU 版 | 神经加法器推理，见 [[ADR-0005-onnx-runtime-cpu-deployment]] |
| Node.js | 22 | 仅构建前端时需要，运行时不需要 |
| 前端 | React + Vite 静态产物 | `npm run build` 生成 `frontend/dist` |
| 反向代理 | Caddy 2（推荐）或 nginx | 同源提供静态页与 `/api`，避免跨域 |

运行时只需要 `fastapi`、`uvicorn`、`pydantic`、`numpy`、`onnxruntime`，不需要 PyTorch。部署使用 `uv sync --no-dev`，既不装开发依赖，也不装训练组 `train`。

## 3. 必需文件与路径

| 路径 | 是否进 Git | 部署时如何获得 |
|---|---|---|
| `backend/app/data/products.json` | 是 | 随代码 |
| `backend/checkpoints/adder-onnx/adder.onnx` | **是**（2026-10-17 起纳入 Git，约 443 KiB） | 随代码克隆获得；升级时 `git pull` 自动更新 |
| SQLite 数据库文件 | **是**（2026-10-17 起随仓库分发，纪念原版丢失的数据） | 克隆即得；生产环境仍建议用 `SUGARMARKET_DB_PATH` 放到 `/var/lib/sugarmarket/`，并以仓库中的文件为初始数据 |
| `frontend/dist/` | 否 | 在部署机或构建机执行 `npm run build` |

数据库默认路径为 `backend/data/sugarmarket.sqlite3`。部署时必须用 `SUGARMARKET_DB_PATH` 改到 `/var/lib/sugarmarket/`，避免代码目录升级时覆盖数据。

## 4. 配置项

| 名称 | 默认值 | 生产建议 | 作用 |
|---|---|---|---|
| `SUGARMARKET_DB_PATH` | `backend/data/sugarmarket.sqlite3` | `/var/lib/sugarmarket/sugarmarket.sqlite3` | 数据库文件 |
| uvicorn `--host` | `127.0.0.1` | `127.0.0.1`（只允许本机反代访问） | API 绑定地址 |
| uvicorn `--port` | `8000` | `8000` | API 端口 |
| uvicorn `--workers` | 1 | **必须为 1** | SQLite 单写者；每个进程各自加载模型，多 worker 没有收益 |
| 结账容量 `MAX_ADDENDS` | `1000`（代码常量） | 不改 | 超过时拒绝结账，见 [[checkout-cart-and-order]] |

没有其他必需的环境变量或密钥。`.env` 文件不需要。

## 5. 网络与安全

- **后台无认证**。对策：只在局域网内开放；不做端口映射到公网。`/#admin` 是前端的哈希路由，服务器看不到 `#` 后的部分，所以无法只拦截后台；若需要额外保护，只能在整站层面加 `basicauth`，这会同时影响顾客页。
- API 进程只监听 `127.0.0.1`，外部只能经 Caddy 访问。
- 防火墙只放行 80（及可选 443）。
- 房间号是唯一顾客标识（见 ADR-0006），系统不保存电话、住址等个人信息。
- 日志默认输出到 systemd journal；不要记录完整请求体。

## 6. 数据与备份

- 数据库是单个 SQLite 文件，`PRAGMA foreign_keys` 已开启。
- 备份用 SQLite 在线备份命令，不要直接复制正在写入的文件，见 [[deployment-tutorial]] 第 9 步。
- 建议每天一次备份，保留 14 份。

## 7. 已知风险（部署前必读）

| 风险 | 后果 | 对策 |
|---|---|---|
| 模型文件缺失或损坏 | `OnnxAdder` 构造失败，异常在 `checkout.py` 的 `try` 块内被捕获，结账按规则**创建免单订单**（第三档），顾客不会看到报错。 | 模型已随 Git 分发（`.gitignore` 为其保留例外），升级后必做冒烟测试（教程第 8 步）。静默免单仍是当前设计的副作用，建议人类裁决是否改为启动时失败（待提出为新问题）。 |
| 后台无认证 | 局域网内任何人可改库存、完成订单 | 仅内网访问；反代加 basicauth（可选） |
| SQLite 单写者 | 并发下单时写锁排队，极端情况下返回 500 | 单店规模无需处理；`--workers 1` |
| 部署目录被 git 清理 | 误删模型或数据库 | 数据库放 `/var/lib`；模型单独备份 |
| 依赖的 `onnxruntime` 版本升级 | 数值可能微变 | 只按 `uv.lock` 安装，升级前跑 `uv run pytest` |

## 8. 验收清单

部署完成后逐项确认：

- [ ] `curl http://<服务器>/api/products` 返回 100 个商品左右的 JSON，价格为元字符串。
- [ ] 打开首页，分类、商品卡、购物袋动效正常。
- [ ] 在**临时数据库**上完成一次结账，`tier` 为 `none`（不是 `tier3_free`）。
- [ ] `/#admin` 可以登录（输入任意内容），订单列表可以打开。
- [ ] 外网无法直接访问 8000 端口。
- [ ] 重启服务器后 systemd 自动拉起 API，数据仍在。
- [ ] 备份脚本可以生成有效的 SQLite 备份文件。

## 9. 关联文档

- 操作教程：[[deployment-tutorial]]
- 数据库：[[products-table]]、[[orders-table]]
- API：[[products-list-api]]、[[checkout-api]]、[[admin-api]]
- 决策：[[ADR-0005-onnx-runtime-cpu-deployment]]、[[ADR-0006-checkout-room-identity-and-stock-reservation]]
