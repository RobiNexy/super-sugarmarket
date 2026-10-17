# Sugarmarket 部署教程

适用环境：Ubuntu 22.04/24.04 或 Debian 12，单机，局域网访问。
最后更新：2026-10-17
设计与风险见 [[deployment-overview]]。

全程用一个普通用户（下文以 `deploy` 为例）执行，只有“安装系统包”和“写入 /etc、/srv、/var/lib”的命令需要 `sudo`。

---

## 第 1 步：准备系统与工具

```sh
sudo apt update
sudo apt install -y git curl ca-certificates sqlite3 gpg debian-keyring debian-archive-keyring apt-transport-https
```

安装 **uv**（Python 管理器，会自动下载 Python 3.12）：

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env   # 或重新登录，使 uv 在 PATH 中
uv --version
```

安装 **Node.js 22**（只用于构建前端，可在开发机上做，部署机可不装）：

```sh
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
node --version   # 应为 v22.x
```

安装 **Caddy**（反向代理与静态文件服务）：

```sh
sudo curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
caddy version
```

---

## 第 2 步：创建运行用户与目录

```sh
sudo useradd --system --create-home --home-dir /opt/sugarmarket --shell /usr/sbin/nologin sugarmarket
sudo mkdir -p /var/lib/sugarmarket /srv/sugarmarket
sudo chown sugarmarket:sugarmarket /var/lib/sugarmarket
```

- `/opt/sugarmarket`：代码与 Python 环境
- `/var/lib/sugarmarket`：SQLite 数据库（**不要放在代码目录里**）
- `/srv/sugarmarket`：前端静态文件

---

## 第 3 步：获取代码并安装后端依赖

```sh
sudo -u sugarmarket git clone <你的仓库地址> /opt/sugarmarket/app
cd /opt/sugarmarket/app/backend
sudo -u sugarmarket env HOME=/opt/sugarmarket uv sync --no-dev
```

`uv sync --no-dev` 会按 `uv.lock` 安装运行依赖（FastAPI、uvicorn、onnxruntime、numpy 等），不会安装 PyTorch 训练依赖。

验证 Python 环境可以导入应用：

```sh
sudo -u sugarmarket env HOME=/opt/sugarmarket /opt/sugarmarket/app/backend/.venv/bin/python -c "import app.main, onnxruntime; print('ok', onnxruntime.__version__)"
```

---

## 第 4 步：放入神经加法器模型（必须）

模型文件 `adder.onnx` 不在 Git 中。从开发机复制（在开发机上执行）：

```sh
scp backend/checkpoints/adder-onnx/adder.onnx deploy@<服务器>:/tmp/adder.onnx
```

在服务器上放到代码目录的固定位置：

```sh
sudo -u sugarmarket mkdir -p /opt/sugarmarket/app/backend/checkpoints/adder-onnx
sudo mv /tmp/adder.onnx /opt/sugarmarket/app/backend/checkpoints/adder-onnx/adder.onnx
sudo chown sugarmarket:sugarmarket /opt/sugarmarket/app/backend/checkpoints/adder-onnx/adder.onnx
ls -l /opt/sugarmarket/app/backend/checkpoints/adder-onnx/adder.onnx
```

文件大小应为 453,367 字节（约 443 KiB）。缺失时所有结账都会变成免单，见 [[deployment-overview]] 第 7 节。

---

## 第 5 步：构建前端

在开发机或服务器上执行（需要 Node 22）：

```sh
cd frontend
npm ci
npm run build          # 产物在 frontend/dist/
```

把 `dist` 放到服务目录（在服务器上执行，若在开发机构建则先 `scp -r dist` 过去）：

```sh
sudo rm -rf /srv/sugarmarket/*
sudo cp -r /opt/sugarmarket/app/frontend/dist/* /srv/sugarmarket/
sudo chown -R root:root /srv/sugarmarket
```

前端只用到相对路径的 `/api`，不需要改任何地址配置。

---

## 第 6 步：配置 API 服务（systemd）

创建服务文件 `/etc/systemd/system/sugarmarket-api.service`：

```ini
[Unit]
Description=Sugarmarket API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=sugarmarket
Group=sugarmarket
WorkingDirectory=/opt/sugarmarket/app/backend
Environment=SUGARMARKET_DB_PATH=/var/lib/sugarmarket/sugarmarket.sqlite3
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/sugarmarket/app/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers
Restart=on-failure
RestartSec=3

# 基本加固
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/sugarmarket
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

启动并设为开机自启：

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now sugarmarket-api
sudo systemctl status sugarmarket-api --no-pager
curl -s http://127.0.0.1:8000/api/products | head -c 200; echo
```

看到 JSON 即表示 API 正常，数据库会在首次启动时自动创建在 `/var/lib/sugarmarket/`。

> `--workers 1` 不可改大：SQLite 只允许一个写者，多 worker 会造成库存判断与订单写入的竞争。

---

## 第 7 步：配置 Caddy

编辑 `/etc/caddy/Caddyfile`（局域网内使用，`:80` 即可；把下面的 `:80` 换成你的内网域名可选）：

```caddyfile
:80 {
    encode zstd gzip

    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    handle {
        root * /srv/sugarmarket
        file_server
    }

    log {
        output stdout
        format console
    }
}
```

检查语法并重载：

```sh
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
```

在局域网另一台设备上打开 `http://<服务器内网IP>/`，应看到商城首页。

> 后台是同一个页面的 `#admin` 片段，服务器无法单独拦截。如需额外限制，只能在整站加 `basicauth`，这会同时影响顾客页，仅在确有需要时使用。

---

## 第 8 步：防火墙与冒烟测试

只放行 HTTP，不放行 8000：

```sh
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw enable
sudo ufw status
```

**冒烟测试必须使用临时数据库**，避免测试订单进入正式数据。在服务器上：

```sh
TMP_DB=/tmp/sugarmarket-smoke.sqlite3
rm -f $TMP_DB
cd /opt/sugarmarket/app/backend
SUGARMARKET_DB_PATH=$TMP_DB sudo -u sugarmarket -E env HOME=/opt/sugarmarket \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8011 --workers 1 &
SMOKE_PID=$!
sleep 5
curl -s -X POST http://127.0.0.1:8011/api/checkout \
  -H 'content-type: application/json' \
  -d '{"room_no":"smoke","items":[{"product_id":1,"quantity":1}]}'
echo
kill $SMOKE_PID   # 若 uvicorn 仍在运行：pkill -f 'port 8011'
rm -f $TMP_DB
```

预期返回 `"tier":"none"` 且 `"total_yuan":"2.00"`。若返回 `"tier":"tier3_free"`，说明模型没有被加载，回到第 4 步检查文件。

---

## 第 9 步：数据库备份

创建备份脚本 `/usr/local/bin/sugarmarket-backup`（权限 755）：

```sh
#!/bin/sh
set -eu
SRC=/var/lib/sugarmarket/sugarmarket.sqlite3
DEST_DIR=/var/backups/sugarmarket
mkdir -p "$DEST_DIR"
STAMP=$(date +%Y%m%d-%H%M%S)
sqlite3 "$SRC" ".backup '$DEST_DIR/sugarmarket-$STAMP.sqlite3'"
ls -1t "$DEST_DIR"/sugarmarket-*.sqlite3 | tail -n +15 | xargs -r rm -f
echo "backup ok: $STAMP"
```

每天 03:00 执行，写入 root 的 crontab（`sudo crontab -e`）：

```cron
0 3 * * * /usr/local/bin/sugarmarket-backup >> /var/log/sugarmarket-backup.log 2>&1
```

恢复时先停服务，再把备份文件复制回 `/var/lib/sugarmarket/sugarmarket.sqlite3`，再启动服务。

---

## 第 10 步：升级

```sh
cd /opt/sugarmarket/app
sudo -u sugarmarket git pull
cd backend && sudo -u sugarmarket env HOME=/opt/sugarmarket uv sync --no-dev && cd ..
cd frontend && npm ci && npm run build && cd ..
sudo rm -rf /srv/sugarmarket/* && sudo cp -r frontend/dist/* /srv/sugarmarket/
sudo systemctl restart sugarmarket-api
```

升级前先执行第 9 步备份。升级后重做第 8 步冒烟测试。

**回滚**：`git checkout <上一个提交>`，重复上面的构建与复制步骤，并恢复升级前的数据库备份（若升级改动了数据结构）。

---

## 第 11 步：常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 首页空白或 404 | `/srv/sugarmarket` 没有 `index.html` | 重做第 5 步的复制 |
| 商品页“货架联系不上” | API 没起来或 Caddy 未代理 | `systemctl status sugarmarket-api`；`journalctl -u sugarmarket-api -n 50` |
| Caddy 返回 502 | uvicorn 未监听 8000 | 同上，检查 `ExecStart` 路径 |
| 所有结账都是免单 | 模型文件缺失或被移动 | 第 4 步；冒烟测试 |
| 启动报 `database is locked` | 有另一个进程在写同一个数据库 | 确认只有一个 uvicorn；不要用 `--workers` 大于 1 |
| 数据库没有数据 | 数据库路径错误 | 检查 `Environment=SUGARMARKET_DB_PATH`，`ls -l /var/lib/sugarmarket` |
| 升级后商品没变化 | 种子数据只增量补入缺失 ID，不覆盖已有商品 | 在后台手动修改，或备份后删除对应行再启动（需人类确认） |

日志查看：

```sh
journalctl -u sugarmarket-api -f
journalctl -u caddy -f
```

---

## 附：部署完成检查表

- [ ] 第 3 步 `import app.main` 成功
- [ ] 第 4 步模型文件存在（453,367 字节）
- [ ] 第 6 步 systemd 服务 `active (running)`，重启后仍运行
- [ ] 第 7 步 Caddy 能访问首页与 `/api/products`
- [ ] 第 8 步冒烟测试结果为 `tier:none`
- [ ] 第 9 步备份脚本成功生成文件
- [ ] 8000 端口不能从其他机器访问

完成后，把“部署时间、服务器地址、模型文件来源版本”记录到 [[current-project-state]] 的最近关键变更里。
