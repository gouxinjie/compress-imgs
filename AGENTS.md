# AGENTS.md

## 项目定位

这是一个类似 TinyPNG 的个人图片压缩工具 MVP。
目标是尽快做出可用版本，不追求复杂架构。

## 技术选型

- 后端使用 `FastAPI`
- 页面模板使用 `Jinja2Templates`
- 前端使用原生 `JavaScript` + 简单 `CSS`
- 图片压缩使用 `tinify`
- 运行方式以单机部署为前提，适合低并发场景

## MVP 范围

- 支持拖拽上传和点击选择文件
- 单次最多上传 `10` 张图片
- 支持格式：`png`、`jpg`、`jpeg`、`webp`
- 单文件最大 `10 MB`
- 单次请求总大小最大 `100 MB`
- 上传后立即进入压缩流程
- 展示每张图片的压缩结果、状态、大小变化
- 成功图片支持单张下载
- 成功图片不少于 `2` 张时支持打包 `ZIP` 下载

## 明确不做

- 不做登录、注册、套餐、支付
- 不做数据库
- 不做消息队列
- 不做 WebSocket
- 不做多 key 调度
- 不做后台管理系统

## 实现原则

- 采用前后端一体方案，不拆成独立前端项目
- 第一阶段优先可用，不引入复杂基础设施
- 前端先做基础校验，后端必须再次严格校验
- 失败文件不能影响成功文件展示和下载
- 不伪造压缩百分比

## 核心流程

### 上传阶段

- 前端通过 `XMLHttpRequest.upload.onprogress` 展示真实上传进度
- 提交到 `POST /api/compress`

### 压缩阶段

- 后端创建 `task_id`
- 使用任务文件记录处理中状态
- 前端通过轮询 `GET /api/tasks/{task_id}` 获取进度
- 压缩阶段展示“已完成 X / Y”，不要展示伪造百分比

### 结果阶段

- 结果页路径为 `GET /result/{task_id}`
- 单图下载路径为 `GET /download/{task_id}/{filename}`
- 全部下载路径为 `GET /download/{task_id}/all.zip`

## 状态约定

### 任务状态

- `queued`
- `processing`
- `partial_success`
- `completed`
- `failed`

### 文件状态

- `queued`
- `processing`
- `success`
- `failed`

## 存储约定

使用本地临时目录，不接数据库。

- `work/tmp/runtime/uploads/`：原图
- `work/tmp/runtime/compressed/{task_id}/`：压缩结果
- `work/tmp/runtime/zips/`：ZIP 文件
- `work/tmp/runtime/tasks/`：任务 JSON

临时文件应支持过期清理，目标清理时间为 `30` 分钟。

## 静态资源约定

- 网站图标、头部图标、功能图标、场景图等统一放在 `assets/`
- 页面中通过 `/assets/...` 引用资源
- 未被代码引用的图片不应长期保留在仓库中

## 推荐目录

```text
app/
  main.py
  config.py
  routes/
    pages.py
    api.py
  services/
    compressor.py
    file_store.py
    zip_service.py
    limiter.py
    cleanup.py
    task_store.py
  templates/
    base.html
    index.html
    result.html
  static/
    css/
      app.css
    js/
      common.js
      upload.js
      result.js
  models/
    schemas.py
assets/
work/
  tmp/
    runtime/
      uploads/
      compressed/
      zips/
      tasks/
tests/
```

## 开发优先级

1. 先搭好 `FastAPI + Jinja2` 基础骨架
2. 先完成首页上传体验
3. 再完成 `/api/compress` 和任务轮询
4. 再接入 `tinify`
5. 最后补结果页、ZIP 下载、限流、清理逻辑

## 协作要求

- 所有实现以当前 MVP 文档为准，避免擅自扩展需求
- 新增代码时优先保持简单、可读、可维护
- 如果要增加超出 MVP 的能力，应先确认是否真的需要

## Git 约定

- 当前仓库默认分支为 `main`
- 远端名统一使用 `origin`
- `origin` 的拉取地址为 GitHub
- `origin` 的推送地址同时包含 GitHub 和 Gitee
- 后续提交后，默认执行一次 `git push origin main`，应同时推送到这两个仓库：
  - `https://github.com/gouxinjie/compress-imgs.git`
  - `https://gitee.com/gou-xinjie/compress-imgs.git`
