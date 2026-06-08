# FastAPI + Jinja2 图片压缩站 MVP 设计

## 一、项目目标

做一个类似 TinyPNG 的个人图片压缩网站，满足以下约束：

- 前后端一体
- 支持拖拽上传
- 单次最多上传 10 张图片
- 当前只有 1 个 Tinify key
- 面向低并发个人项目
- 部署在 ECS，使用本地临时目录

## 二、MVP 功能范围

### 1. 上传与压缩

- 支持拖拽上传
- 支持点击选择文件
- 单次最多上传 10 张
- 支持格式：`.png`、`.jpg`、`.jpeg`、`.webp`
- 单文件大小限制：`10 MB`
- 单次请求总大小限制：`100 MB`
- 前端先校验，后端再做一次强校验
- 上传完成后立即进入压缩流程
- 第一阶段不做复杂任务队列

### 2. 结果展示

- 展示原文件名
- 展示原始大小
- 展示压缩后大小
- 展示压缩率
- 展示每张图的状态：成功或失败
- 成功图片支持单独下载
- 当成功图片不少于 2 张时，支持 ZIP 打包下载

### 3. 失败处理

需要覆盖以下失败场景：

- 文件格式不支持
- 文件数量超过 10
- 文件体积超限
- 请求总大小超限
- Tinify key 无效
- Tinify 当月额度耗尽
- Tinify 接口请求失败
- 本地临时目录不可写

要求失败文件不影响成功文件的展示和下载。

### 4. 基础防滥用

- 基于 IP 做简单限流
- 单次请求最多 10 张
- 限制单文件大小
- 限制总请求体大小
- 对超限请求直接拒绝

第一阶段不做登录、套餐、数据库用户系统。

## 三、整体架构

### 后端

- FastAPI
- Jinja2Templates
- `python-multipart`
- `tinify`
- `uvicorn`

### 前端

- Jinja2 服务端模板
- 原生 JavaScript 处理拖拽上传和 AJAX 请求
- 简单 CSS

### 存储

在 ECS 上使用本地临时目录：

- `work/tmp/uploads/`：保存原图
- `work/tmp/compressed/{task_id}/`：保存压缩结果
- `work/tmp/zips/`：保存 ZIP 包
- `work/tmp/tasks/`：保存任务元数据 JSON

所有临时文件在 `30-60` 分钟后自动清理。

## 四、推荐目录结构

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
    partials/
      upload_zone.html
      result_card.html
  static/
    css/
      app.css
    js/
      upload.js
      result.js
  models/
    schemas.py
work/
  tmp/
    uploads/
    compressed/
    zips/
    tasks/
.env
requirements.txt
```

## 五、核心处理模型

这个项目建议采用“两段式体验”，不要伪造一个看起来精确但实际上不真实的压缩百分比。

### 第一阶段：上传进度

前端使用 `XMLHttpRequest` 的 `upload.onprogress`：

- 这是真实上传进度
- 进度依据是浏览器上传到 ECS 的字节数
- 适合展示 `0% - 100%` 的进度条

### 第二阶段：压缩进度

上传完成后，前端切换到压缩阶段：

- 不显示伪造的 `67% 压缩中`
- 改为展示任务进度，例如 `已完成 3 / 8`
- 每压缩完一张，就更新一张结果卡片

### 压缩进度回传方式

为了让前端拿到“已完成几张”的中间状态，不能只靠一个同步接口一次性返回结果。第一阶段推荐用“创建任务 + 轮询任务状态”的方式：

1. `POST /api/compress`
   - 接收文件
   - 创建 `task_id`
   - 写入初始任务状态
   - 开始逐张压缩
   - 立即返回 `task_id`
2. 前端每 `800-1200ms` 轮询一次 `GET /api/tasks/{task_id}`
3. 后端在每张图片压缩完成后，更新任务 JSON
4. 当前端发现任务完成后，跳转结果页或原地渲染最终结果

这样实现简单，适合单机 ECS，不需要 WebSocket，也不需要消息队列。

## 六、任务状态设计

### 任务状态

后端任务建议使用以下状态：

- `queued`
- `processing`
- `partial_success`
- `completed`
- `failed`

状态含义：

- `queued`：任务已创建，尚未开始处理
- `processing`：正在逐张压缩
- `partial_success`：有成功也有失败，且已处理完毕
- `completed`：全部成功，且已处理完毕
- `failed`：任务级失败，例如 key 无效、目录不可写、请求体非法

### 文件状态

单文件状态建议使用：

- `queued`
- `processing`
- `success`
- `failed`

## 七、页面交互设计

### 1. 首页 `/`

#### 页面组成

- 标题
- 简短说明
- 拖拽上传区
- 文件规则说明
- 待上传文件列表
- 全局进度区域
- 提交按钮
- 错误提示区域

#### 拖拽上传区状态

- `idle`
  - 默认虚线边框
  - 文案：拖拽图片到这里，或点击选择
- `dragover`
  - 高亮边框和背景
- `invalid`
  - 提示格式不支持或数量超限
- `disabled`
  - 上传过程中不可继续拖入

### 2. 待上传文件列表

每个文件展示一行：

- 文件名
- 可读文件大小
- 本地校验结果
- 移除按钮

每个文件的前端状态建议有：

- `ready`
- `invalid_type`
- `too_large`
- `removed`

### 3. 提交流程

用户点击“开始压缩”后：

1. 前端校验文件数量、格式和大小
2. 禁用提交按钮
3. 禁用拖拽区域
4. 显示全局进度面板
5. 通过 AJAX 上传文件到 `/api/compress`
6. 上传完成后切换到“压缩中”状态
7. 轮询任务状态接口
8. 任务结束后跳转结果页

## 八、全局进度面板设计

### 1. 上传中状态

- 标题：`正在上传文件`
- 进度条：真实上传百分比
- 辅助文案：`正在上传 4 个文件...`

### 2. 压缩中状态

- 标题：`正在压缩图片`
- 不显示伪百分比
- 展示文案：`已完成 2 / 4`
- 当前项文案：`正在处理 banner-homepage.png`

### 3. 完成状态

- 标题：`压缩完成`
- 展示成功数和失败数
- 提供查看结果或直接下载入口

### 4. 失败状态

- 标题：`请求失败`
- 展示错误原因
- 提供重试按钮
- 尽量保留用户已选择的文件列表

## 九、结果页 `/result/{task_id}`

### 1. 顶部汇总区

- 总文件数
- 成功数
- 失败数
- 原始总大小
- 压缩后总大小
- 节省总大小

### 2. 单文件结果卡片

每张图展示：

- 文件名
- 状态标签
- 原始大小
- 压缩后大小
- 节省比例
- 成功时显示下载按钮
- 失败时显示错误信息

### 3. 结果页操作

- 成功文件不少于 2 张时显示 `下载全部 ZIP`
- 显示 `继续压缩图片`

## 十、路由设计

### 页面路由

- `GET /`
  - 上传首页
- `GET /result/{task_id}`
  - 结果页

### API 路由

- `POST /api/compress`
  - 接收文件并创建任务
  - 返回 `task_id`
- `GET /api/tasks/{task_id}`
  - 返回当前任务状态、完成数量、结果列表
- `GET /download/{task_id}/{filename}`
  - 下载单张压缩图
- `GET /download/{task_id}/all.zip`
  - 下载 ZIP
- `GET /health`
  - 健康检查

## 十一、任务元数据落盘设计

由于第一阶段不使用数据库，结果页必须依赖本地 JSON 恢复任务数据。

### 任务文件位置

- `work/tmp/tasks/{task_id}.json`

### 任务文件用途

- 供前端轮询读取任务进度
- 供结果页读取最终结果
- 供清理程序判断是否过期

### 任务 JSON 结构建议

```json
{
  "task_id": "task_20260608_ab12cd",
  "status": "processing",
  "created_at": "2026-06-08T11:30:00+08:00",
  "updated_at": "2026-06-08T11:30:05+08:00",
  "total": 4,
  "processed": 2,
  "success": 2,
  "failed": 0,
  "items": [
    {
      "filename": "hero.png",
      "stored_filename": "hero.png",
      "status": "success",
      "original_size": 2400345,
      "compressed_size": 823211,
      "ratio": 65.7,
      "download_path": "/download/task_20260608_ab12cd/hero.png",
      "error_code": null,
      "error_message": null
    },
    {
      "filename": "logo.webp",
      "stored_filename": "logo_2.webp",
      "status": "processing",
      "original_size": 80444,
      "compressed_size": null,
      "ratio": null,
      "download_path": null,
      "error_code": null,
      "error_message": null
    }
  ],
  "zip_download_path": null
}
```

## 十二、API 返回结构建议

### `POST /api/compress`

上传成功后立即返回：

```json
{
  "task_id": "task_20260608_ab12cd",
  "status": "queued",
  "poll_url": "/api/tasks/task_20260608_ab12cd"
}
```

### `GET /api/tasks/{task_id}`

处理中或完成后返回：

```json
{
  "task_id": "task_20260608_ab12cd",
  "status": "processing",
  "summary": {
    "total": 4,
    "processed": 2,
    "success": 2,
    "failed": 0,
    "original_bytes": 7340032,
    "compressed_bytes": 2211264,
    "saved_bytes": 5128768
  },
  "items": [
    {
      "filename": "hero.png",
      "status": "success",
      "original_size": 2400345,
      "compressed_size": 823211,
      "ratio": 65.7,
      "download_path": "/download/task_20260608_ab12cd/hero.png",
      "error_code": null,
      "error_message": null
    }
  ],
  "zip_download_path": null
}
```

## 十三、错误码与文案映射

建议后端统一返回错误码，前端根据错误码展示文案。

### 任务级错误码

- `too_many_files`
- `request_too_large`
- `invalid_api_key`
- `quota_exceeded`
- `storage_unavailable`
- `rate_limited`
- `server_error`

### 文件级错误码

- `invalid_file_type`
- `file_too_large`
- `compress_failed`

### 默认文案建议

- `too_many_files`：上传数量不能超过 10 张
- `request_too_large`：本次上传总大小超过限制
- `invalid_api_key`：压缩服务配置异常
- `quota_exceeded`：本月压缩额度已用完
- `storage_unavailable`：临时存储不可用，请稍后再试
- `rate_limited`：请求过于频繁，请稍后再试
- `invalid_file_type`：仅支持 PNG、JPG、JPEG、WEBP
- `file_too_large`：单张图片不能超过 10 MB
- `compress_failed`：该图片压缩失败，请重试
- `server_error`：服务暂时不可用，请稍后再试

## 十四、同名文件处理规则

同一次上传中，可能出现多个同名文件，例如两个 `image.png`。

建议规则如下：

- 展示给用户看的 `filename` 保持原名
- 实际保存在磁盘的 `stored_filename` 做去重
- 去重方式示例：
  - `image.png`
  - `image_2.png`
  - `image_3.png`

这样既能保证下载路径唯一，也能避免文件互相覆盖。

## 十五、上传大小限制落地方式

### 1. 前端限制

- 文件加入列表时校验单文件大小
- 提交前校验文件总数和总大小
- 超限时直接阻止提交

### 2. FastAPI 应用层限制

- 在 `/api/compress` 中校验上传文件数量
- 逐个检查文件大小
- 汇总所有文件大小
- 超限时返回 `413` 或 `400`

### 3. Nginx 层限制

部署到 ECS 后，反向代理建议配置：

```nginx
client_max_body_size 100M;
```

这样可以避免超大请求先进入应用层，减少无意义的磁盘和内存占用。

### 4. 临时文件位置说明

`UploadFile` 在处理上传时可能使用临时文件，因此需要明确：

- ECS 上要有可写临时目录
- 应用启动时检查 `work/tmp` 是否存在且可写
- 定期清理过期文件

## 十六、后端模块职责

### `config.py`

负责读取 `.env` 并暴露：

- `TINIFY_API_KEY`
- `MAX_FILES_PER_UPLOAD=10`
- `MAX_FILE_SIZE_MB=10`
- `MAX_REQUEST_SIZE_MB=100`
- `TEMP_DIR=work/tmp`
- `FILE_EXPIRE_MINUTES=60`
- `POLL_INTERVAL_MS=1000`

### `services/compressor.py`

职责：

- 初始化 Tinify
- 压缩单张图片
- 统一转换 Tinify 异常
- 返回结果元数据和错误码

### `services/file_store.py`

职责：

- 生成 `task_id`
- 保存原图
- 保存压缩结果
- 生成安全下载路径
- 处理同名文件去重
- 汇总大小统计

### `services/task_store.py`

职责：

- 创建任务 JSON
- 读取任务 JSON
- 更新任务状态
- 写入逐文件结果
- 更新汇总信息

### `services/zip_service.py`

职责：

- 将成功图片打包成 ZIP
- 返回 ZIP 路径

### `services/limiter.py`

职责：

- 基于内存做简单 IP 限流
- 例如每分钟最多 `5` 次上传请求

### `services/cleanup.py`

职责：

- 清理过期临时文件
- 清理原图、压缩图、ZIP、任务 JSON
- 启动时执行一次
- 周期性执行
- 也可以在上传请求结束后顺带执行一次

## 十七、前端状态模型

页面级状态建议：

```js
const pageState = {
  IDLE: "idle",
  READY: "ready",
  UPLOADING: "uploading",
  COMPRESSING: "compressing",
  COMPLETED: "completed",
  ERROR: "error"
};
```

文件级状态建议：

```js
const fileState = {
  READY: "ready",
  INVALID: "invalid",
  QUEUED: "queued",
  PROCESSING: "processing",
  SUCCESS: "success",
  FAILED: "failed"
};
```

## 十八、页面文案建议

- `拖拽最多 10 张图片到这里`
- `支持 PNG、JPG、JPEG、WEBP`
- `单张图片最大 10 MB`
- `本次上传总大小不能超过 100 MB`
- `正在上传文件...`
- `正在压缩图片...`
- `已完成 3 / 6`
- `当前个人工具暂时不可用`
- `本月压缩额度已用完`

## 十九、ECS 部署适配建议

这套方案适合部署在 ECS，原因是：

- 并发低
- 本地临时文件足够应付
- 有过期清理，不会无限增长
- 第一阶段不需要 Redis 和数据库

建议的清理规则：

- 原图、压缩图、ZIP、任务 JSON 在 `60` 分钟后删除
- 即使用户提前下载，也可以仍然保留到过期时间，逻辑更简单

## 二十、第一阶段不做的功能

- 登录注册
- 数据库
- 用户历史记录
- URL 压缩
- 多 key 切换
- 支付
- 管理后台
- WebSocket 实时进度

## 二十一、开发顺序

1. 搭好 FastAPI 和 Jinja2 基础骨架
2. 完成首页布局
3. 完成拖拽上传和 AJAX 上传
4. 实现 `/api/compress`
5. 实现 `/api/tasks/{task_id}`
6. 接入 Tinify 压缩服务
7. 完成任务 JSON 存储
8. 完成结果页
9. 增加 ZIP 下载
10. 增加限流和过期清理

## 二十二、下一步编码入口

建议先从以下文件开始：

- `app/main.py`
- `app/config.py`
- `app/routes/pages.py`
- `app/routes/api.py`
- `app/services/task_store.py`
- `app/templates/index.html`
- `app/static/js/upload.js`
