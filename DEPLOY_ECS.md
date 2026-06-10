# CompressImgs GitHub Actions 自动部署到 ECS

本文档说明如何把当前项目通过 GitHub Actions 自动部署到 ECS 的：

```text
/var/www/compress-imgs
```

本文档只保留一种配置方式：

- 代码通过 GitHub Actions 自动发布
- 生产环境 `.env` 由你手工放到 ECS 本机
- `TINIFY_API_KEY` 只保存在 ECS 本机 `.env`

当前项目特征：

- 应用：`FastAPI + Jinja2`
- 进程模型：单机单实例
- 存储：本地临时文件，无数据库
- 任务状态：本地 JSON
- 运行时目录：`work/tmp/runtime/`

这套方案适合单台 ECS，不适合直接做多实例负载均衡。

## 1. 部署后的访问方式

推荐访问地址：

- 首页：`https://process-imgs.gouxinjie.com/`
- 健康检查：`https://process-imgs.gouxinjie.com/api/health`

如果临时还没配域名，也可以先用公网 IP 验证：

- `http://ECS公网IP/`
- `http://ECS公网IP/api/health`

不建议长期直接暴露 `8000`。`8000` 只适合临时调试：

- `http://ECS公网IP:8000/`

## 2. 自动部署的整体流程

流程是：

1. 你把代码 push 到 GitHub 的 `main`
2. GitHub Actions 触发部署工作流
3. 工作流通过 SSH 连接 ECS
4. 代码先同步到 ECS 上的临时发布目录
5. 服务器把代码发布到 `/var/www/compress-imgs`
6. 仅删除“上一次由仓库管理、这次已不存在”的旧文件
7. 安装或更新 Python 依赖
8. 重启 `process-imgs` systemd 服务
9. 轮询 `/api/health`，确认服务真的已经起来

仓库里已经提供：

- 工作流文件：[.github/workflows/deploy-ecs.yml](</D:/MyProjects/compress-imgs/.github/workflows/deploy-ecs.yml>)
- ECS 部署脚本：[deploy/deploy_on_ecs.sh](</D:/MyProjects/compress-imgs/deploy/deploy_on_ecs.sh>)

## 3. 你需要提前准备什么

### ECS 机器

建议：

- 系统：`Ubuntu 22.04 LTS`
- 配置：`1C2G` 起步
- 有公网 IP

### 二级域名

你的 ECS 已经在用二级域名区分项目，那么这个项目继续沿用同样方式即可：

- `process-imgs.gouxinjie.com`

你只需要新增：

- 一条 DNS 解析
- 一个 Nginx `server` 配置
- 一个 HTTPS 证书

### GitHub 仓库

需要把项目放在 GitHub 仓库中，并且你对仓库有 Settings 权限，能够配置：

- `Secrets and variables`
- `Actions`

### Tinify Key

生产建议准备可用的：

- `TINIFY_API_KEY`

注意：

- `TINIFY_API_KEY` 不放 GitHub Secrets
- `TINIFY_API_KEY` 只保存在 ECS 本机 `/var/www/compress-imgs/.env`

## 4. ECS 首次初始化

GitHub Actions 只负责发版和重启服务，不能替代首台机器的初始化。第一次需要你手工把 ECS 准备好。

### 4.1 安装基础软件

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git rsync
```

### 4.2 创建统一的部署用户和部署目录

下面文档统一假设：

- ECS 上用于 SSH 发布的用户：`deploy`
- systemd 运行用户：`deploy`
- GitHub Secret `ECS_USER`：`deploy`

如果你用的不是 `deploy`，请整篇文档一起替换，不要混用 `$USER`、`root`、`www-data`、`deploy`。

创建用户和目录：

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo mkdir -p /var/www/compress-imgs
sudo chown -R deploy:deploy /var/www/compress-imgs
```

后续要保持一致：

- GitHub Actions 用 `deploy` 这个账号 SSH 到 ECS
- `process-imgs.service` 也用 `deploy` 运行
- `/var/www/compress-imgs` 目录也归 `deploy` 所有

### 4.3 手工创建生产 `.env`

切换到部署用户后，在 ECS 上手工创建：

```bash
sudo -u deploy -H bash -lc 'cd /var/www/compress-imgs && nano .env'
```

内容示例：

```env
TINIFY_API_KEY=你的_tinify_key
MAX_FILES_PER_UPLOAD=10
MAX_FILE_SIZE_MB=10
MAX_REQUEST_SIZE_MB=100
TEMP_DIR=work/tmp
FILE_EXPIRE_MINUTES=30
POLL_INTERVAL_MS=1000
RATE_LIMIT_PER_MINUTE=5
```

说明：

- `TINIFY_API_KEY` 就放在这台 ECS 的 `/var/www/compress-imgs/.env`
- 这个 `.env` 保存在 ECS 本机，不会被 GitHub Actions 覆盖
- 当前工作流会显式排除 `.env`
- GitHub Actions 不需要也不应该持有生产 `TINIFY_API_KEY`

也就是说：

- GitHub Actions 负责发版
- ECS 本机 `.env` 负责保存生产配置和密钥

### 4.4 准备运行目录

```bash
sudo -u deploy -H bash -lc 'mkdir -p /var/www/compress-imgs/work/tmp'
```

## 5. 配置 systemd 服务

创建服务文件：

```bash
sudo nano /etc/systemd/system/process-imgs.service
```

写入：

```ini
[Unit]
Description=Process Imgs FastAPI Service
After=network.target

[Service]
Type=simple
User=deploy
Group=deploy
WorkingDirectory=/var/www/compress-imgs
ExecStart=/var/www/compress-imgs/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

注意：

- 这里示例统一使用 `deploy` 用户运行服务
- `WorkingDirectory` 和 `ExecStart` 都已经对齐到 `/var/www/compress-imgs`
- 这样目录拥有者、systemd 用户、GitHub Actions SSH 用户保持一致

加载并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable process-imgs
sudo systemctl start process-imgs
```

检查状态：

```bash
sudo systemctl status process-imgs
```

## 6. 给部署用户开放重启服务权限

GitHub Actions 通过 SSH 登录 ECS 后，需要执行：

```bash
sudo systemctl restart process-imgs
sudo systemctl status process-imgs
```

所以部署用户需要有免密码执行这两个命令的权限。

编辑 sudoers：

```bash
sudo visudo
```

加入一行，假设部署用户是 `deploy`：

```text
deploy ALL=NOPASSWD: /bin/systemctl restart process-imgs, /bin/systemctl status process-imgs
```

如果你的系统里 `systemctl` 路径不是 `/bin/systemctl`，先确认：

```bash
which systemctl
```

然后把 sudoers 里的路径改成实际值。

## 7. 配置 Nginx

创建站点配置：

```bash
sudo nano /etc/nginx/sites-available/process-imgs
```

写入：

```nginx
server {
    listen 80;
    server_name process-imgs.gouxinjie.com;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/process-imgs /etc/nginx/sites-enabled/process-imgs
sudo nginx -t
sudo systemctl reload nginx
```

## 8. 配置 HTTPS

安装证书工具：

```bash
sudo apt install -y certbot python3-certbot-nginx
```

申请证书：

```bash
sudo certbot --nginx -d process-imgs.gouxinjie.com
```

验证续期：

```bash
sudo certbot renew --dry-run
```

完成后访问：

```text
https://process-imgs.gouxinjie.com/
```

## 9. 配置 ECS 安全组

建议：

- `22`：只允许你的办公 IP 或家庭 IP
- `80`：公网开放
- `443`：公网开放

不建议长期开放：

- `8000`

## 10. 在 GitHub 仓库里配置 Secrets

打开 GitHub 仓库：

```text
Settings -> Secrets and variables -> Actions
```

添加这些 `Repository secrets`：

### `ECS_HOST`

ECS 公网 IP 或域名，例如：

```text
47.xxx.xxx.xxx
```

### `ECS_USER`

用于 SSH 登录 ECS 的用户，这里就是：

```text
deploy
```

### `ECS_SSH_PRIVATE_KEY`

部署用户对应的私钥内容，通常是整段：

```text
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

### `ECS_PORT`

可选。默认 `22`。如果你 SSH 端口不是 22，再加这个 secret。

注意：

- `TINIFY_API_KEY` 不放 GitHub Secrets
- `TINIFY_API_KEY` 只保存在 ECS 本机 `/var/www/compress-imgs/.env`

## 11. 给 GitHub Actions 准备 SSH Key

在你本地机器生成一对专门用于部署的密钥：

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ./deploy_ed25519
```

说明：

- 私钥内容放到 GitHub secret `ECS_SSH_PRIVATE_KEY`
- 公钥内容追加到 ECS 上部署用户的 `~/.ssh/authorized_keys`

把公钥追加到 ECS：

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
cat deploy_ed25519.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

## 12. 仓库里的 GitHub Actions 工作流说明

工作流文件在：

- [.github/workflows/deploy-ecs.yml](</D:/MyProjects/compress-imgs/.github/workflows/deploy-ecs.yml>)

当前行为是：

- 监听 `main` 分支 push
- 支持手动触发 `workflow_dispatch`
- 把代码先同步到 ECS 临时发布目录
- 再发布到 `/var/www/compress-imgs`
- 不会覆盖 `.env`
- 不会覆盖 `work/tmp`
- 会按发布清单删除“仓库里已删掉、服务器上仍残留”的旧受管文件
- 在 ECS 上执行 [deploy/deploy_on_ecs.sh](</D:/MyProjects/compress-imgs/deploy/deploy_on_ecs.sh>)
- 重启 `process-imgs` 服务
- 通过 `/api/health` 做重启后的健康检查

## 13. 首次上线前建议手工跑一次

在 ECS 上先手工跑一遍，确认服务可以正常启动：

```bash
sudo -u deploy -H bash -lc '
  cd /var/www/compress-imgs &&
  python3 -m venv .venv &&
  .venv/bin/pip install -r requirements.txt &&
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
'
```

本机检查：

```bash
curl http://127.0.0.1:8000/api/health
```

返回类似：

```json
{"status":"ok","app":"CompressImgs"}
```

确认正常后再停掉，交给 systemd：

```bash
Ctrl + C
sudo systemctl start process-imgs
```

## 14. 如何触发自动部署

### 方式 A：push 到 main

```bash
git push origin main
```

GitHub Actions 会自动开始部署。

### 方式 B：手动触发

打开 GitHub 仓库：

```text
Actions -> Deploy To ECS -> Run workflow
```

## 15. 部署后怎么访问

如果已经配置好二级域名和 HTTPS：

- `https://process-imgs.gouxinjie.com/`
- `https://process-imgs.gouxinjie.com/api/health`

如果只是临时验证公网 IP：

- `http://ECS公网IP/`
- `http://ECS公网IP/api/health`

### 结果页

结果页地址格式是：

```text
/result/{task_id}
```

例如：

```text
https://process-imgs.gouxinjie.com/result/task_20260609_123456_ab12cd
```

用户正常使用时不需要手输这个地址，前端会在压缩完成后给出“查看结果”入口。

## 16. 一次部署失败时怎么排查

### 看 GitHub Actions 日志

打开：

```text
GitHub -> Actions -> Deploy To ECS
```

重点看失败在哪一步：

- SSH 连接失败
- rsync 同步失败
- pip 安装失败
- systemd 重启失败
- 健康检查失败

### 看 ECS 服务日志

```bash
sudo journalctl -u process-imgs -n 100 --no-pager
sudo journalctl -u process-imgs -f
```

### 看 Nginx 日志

```bash
sudo tail -n 100 /var/log/nginx/access.log
sudo tail -n 100 /var/log/nginx/error.log
```

## 17. 常见问题

### 1. GitHub Actions 能连上 ECS，但重启服务失败

通常是部署用户没有 `sudo systemctl restart process-imgs` 权限。

先检查：

```bash
sudo -n systemctl restart process-imgs
```

如果报权限错误，就回到第 6 节处理 sudoers。

### 2. 工作流执行成功，但网站打不开

检查：

- `process-imgs` 服务是否正常运行
- Nginx 是否正常
- ECS 安全组是否放通 `80/443`
- 域名是否已解析到 ECS 公网 IP
- `/api/health` 是否可访问

### 3. 上传时报 413

检查：

- Nginx 是否配置了 `client_max_body_size 100M;`
- `.env` 中 `MAX_REQUEST_SIZE_MB` 是否过小

### 4. 文件为什么不是精确 30 分钟删除

当前实现的清理触发时机是：

- 应用启动时
- 创建新压缩任务时

所以它是“目标 30 分钟清理”，不是精确到秒的定时删除。如果以后需要，可以再加独立 `cron` 或 systemd timer。

## 18. 当前方案的限制

- 当前是单机部署，不适合直接横向扩容
- 限流是内存实现，多实例之间不会共享状态
- 上传文件、结果图、ZIP、任务 JSON 都在 ECS 本机磁盘
- 当前同步策略只会清理“仓库受管文件”的历史残留，不会碰 `.env`、`work/tmp`、`.venv`

最后这一点是有意为之，目的是避免部署流程误删运行时数据或本地环境文件。

## 19. 上线检查清单

上线前建议逐项确认：

- ECS 已安装 Python / venv / Nginx / rsync
- `/var/www/compress-imgs/.env` 已创建
- `process-imgs.service` 已创建并可启动
- `process-imgs.service` 运行用户是 `deploy`
- `/var/www/compress-imgs` 目录归 `deploy:deploy`
- 部署用户可 SSH 登录 ECS
- 部署用户可免密码执行：
  - `systemctl restart process-imgs`
  - `systemctl status process-imgs`
- GitHub Secrets 已配置
- Nginx 已生效
- 安全组已开放 `80/443`
- `/api/health` 可访问
