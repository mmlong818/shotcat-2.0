<p align="center">
  <img src="assets/logo.png" alt="shotcat logo" width="520">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.0-C8923E" alt="版本 2.0.0">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-6B7280" alt="PolyForm Noncommercial 许可证"></a>
  <a href="https://github.com/mmlong818/shotcat/commits/master"><img src="https://img.shields.io/github/last-commit/mmlong818/shotcat?label=last%20commit" alt="最近提交"></a>
  <a href="https://github.com/mmlong818/shotcat/stargazers"><img src="https://img.shields.io/github/stars/mmlong818/shotcat?style=flat&label=stars" alt="GitHub Stars"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11 以上">
  <img src="https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white" alt="TypeScript 5">
</p>

<p align="center">
  简体中文 · <a href="README.en.md">English</a>
</p>

# shotcat

面向短剧、漫剧和剧情图像制作的本地工作台。`plotcat` 负责剧本创作，`shotcat` 负责把剧本转化为可确认、可追踪、可批量生成的角色、场景、道具、分镜与关键帧。

当前版本：**2.0.0（独立开发版）**

## 产品界面

所有截图均来自当前 `web/` 工作台的真实项目与实际生成结果。

### 项目总览

![项目总览](docs/assets/readme/overview-2026-08-09.png)

### 角色与派生状态

![角色与派生状态](docs/assets/readme/cast-2026-08-09.png)

### 镜头级分镜

![镜头级分镜](docs/assets/readme/storyboard-2026-08-09.png)

### 关键帧画面工作台

![关键帧画面工作台](docs/assets/readme/frames-2026-08-09.png)

## 当前工作流

```text
项目与剧本
  -> 全文分析、类别提取与资产去重
  -> 角色 / 场景 / 道具基准设定与派生状态
  -> AI 拆镜头、导演校验与定向修正
  -> 镜头提示词与参考图约束
  -> 关键帧单张或批量生成
  -> 全集总览与打包导出
```

### 剧本与设定

- 从全文提取角色、场景、道具和章节信息，先按类别分析与去重，再判断是否需要派生状态。
- 同一角色的年龄、身份和妆造变化使用“基准造型 + 派生状态”管理，避免重复创建近似资产。
- 场景结构和关键道具状态只在产生真实视觉差异时拆分；晨昏、天气和轻微变化由镜头提示词处理。
- 设定图支持参考图约束、批量生成、停止任务、刷新恢复和批量导出。

### 分镜设计

- 分镜生成采用“初稿 + 导演校验”两轮流程，原文逐字覆盖后再落地镜头。
- 每个场景记录固定空间结构、观看方向、可视范围、人物位置、姿态、朝向和视线。
- 没有明确移动或姿态变化时，后镜自动继承前镜状态，避免人物和空间无故漂移。
- 相邻镜头记录动作匹配、视线匹配、视觉重心、因果或反应关系，不再逐句机械配图。
- 导演发现关键问题时先保留完整草稿，再等待用户确认并只修正对应镜头；切换页面不会取消任务。
- 黑场是合法镜头；对白说话者、听者和台词内容分别保存。

### 画面生成

- 每个镜头使用一张可编辑的关键帧提示词，只描述当前图片真实可见的静态内容。
- 角色身份设定与逐镜姿态分开，场景固定结构与当前机位分开，降低跨镜头漂移。
- 关键帧自动关联当前镜头使用的角色、场景和道具参考图。
- 背对镜头或被遮挡的角色不会被要求表现不可见的表情；远景不会依赖瞳孔、泪痕等细节传递剧情。
- 支持单镜生成、整集批量生成、实时执行概况、停止任务、刷新恢复和关键帧打包导出。
- 批量任务中每个镜头完成后会立即刷新缩略图和当前画面，不必等待整批结束。

当前日常流程以关键帧交付为终点。视频生成能力保留在后端，但不是完成图像工作流的前置条件。

## 统一入口与本地数据

日常制作统一使用 `web/` 工作台：<http://127.0.0.1:5273>。它是当前产品界面，也是功能验证和反馈的唯一页面基准。

`app/front/` 是旧 Studio 管理界面，默认端口 `7788`，仅用于维护和历史兼容，不能作为当前工作台的页面比对基准。

项目数据、生成图片和密钥默认只保存在本机：

- 数据库：`app/backend/jellyfish.db`
- 生成文件：`app/backend/local-storage/`
- 环境配置：`app/backend/.env`

Git 只同步代码和文档，不同步这些本地内容。迁移到另一台机器时，需要单独备份数据库与生成文件。

## 目录

| 目录 | 用途 |
| --- | --- |
| `web/` | 当前日常制作工作台，默认端口 `5273`。 |
| `app/backend/` | FastAPI API、SQLite 数据、任务队列、资产、分镜与图片生成。 |
| `bridge/` | 剧本分析、设定抽取、视觉词典、AI 拆镜头和 Pipeline 服务。 |
| `app/front/` | 旧 Studio 管理前端，仅用于维护与历史兼容。 |
| `docs/assets/readme/` | README 使用的版本化产品截图。 |

## 本地启动

### 前置条件

- Python 3.11+
- Node.js 18+ 与 pnpm
- 可用的文字模型和图像模型 API；两类模型可以使用不同供应商、模型和 Key
- 可选：Redis 与 Celery Worker。未配置时任务会回退到后端本地执行。

### 1. 启动后端

```bash
cd app/backend
cp .env.example .env
uv sync --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- API：<http://127.0.0.1:8000>
- 接口文档：<http://127.0.0.1:8000/docs>

需要独立 Worker 时，另开终端：

```bash
cd app/backend
uv run celery -A app.core.celery_app.celery_app worker --loglevel=INFO
```

### 2. 启动 Pipeline 服务

设定抽取、视觉词典和 AI 拆镜头依赖该服务：

```bash
cd bridge
python pipeline_server.py
```

服务地址：<http://127.0.0.1:5280>

### 3. 启动工作台

```bash
cd web
pnpm install
pnpm dev
```

访问：<http://127.0.0.1:5273>

首次打开时，若数据库中没有可用模型，工作台会要求分别填写文字模型和图像模型连接。供应商、模型 ID、API 地址和 Key 可以分别配置，真实 Key 不应提交到仓库。

## 使用顺序

1. 在作品库新建或打开项目，在剧本页填写章节正文。
2. 运行“抽取设定”，检查全文分析后的角色、场景和道具分类。
3. 在设定页确认基准资产与派生状态，完善描述并生成参考图。
4. 在分镜页运行“AI 拆镜头”，查看导演校验结果并确认必要修正。
5. 点击“批量生成本集画面”进入画面工作台，观察每个镜头的提示词与图像生成状态。
6. 检查关键帧、参考图关系和提示词，按需单镜重生成或停止任务。
7. 在画面工作台或总览页批量导出关键帧。

## 开发与验证

当前工作台类型检查与构建：

```bash
cd web
pnpm exec tsc -b
pnpm build
```

后端测试：

```bash
cd app/backend
uv run pytest -q
```

Bridge 规则测试：

```bash
pytest bridge -q
```

旧 Studio 后端 API 变更后，如仍需维护 `app/front/`，再同步其 OpenAPI 客户端：

```bash
cd app/front
pnpm run openapi:update
```

## 许可证

[PolyForm Noncommercial 1.0.0](LICENSE)。允许个人使用、学习、修改和非商业分发；不允许商业用途。

Copyright © 2026 猫叔
