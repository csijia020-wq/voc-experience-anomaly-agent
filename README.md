---
title: VoC Experience Anomaly Agent
emoji: 📊
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# VoC 体验异动分析 Agent

> 这是一个模拟项目和求职作品集项目，用于展示 VoC 体验异动分析 Agent 的产品设计、后端链路、指标计算和大模型报告能力。项目使用模拟数据，不代表真实生产系统或真实业务数据。

## 启动方式

```powershell
python start_servers.py start
```

启动后访问：

- 后端 OpenAPI：http://localhost:8000/openapi.json
- 后端文档：http://localhost:8000/docs
- 前端页面：http://localhost:8080/vibe_coding_prototype.html

检查当前端口是否属于本项目：

```powershell
python start_servers.py check
```

`check` 会验证 8000 端口、OpenAPI 标题、健康检查、`/api/chat/stream` 路径、前端页面、DeepSeek 配置状态和 Demo 稳定模式。如果 8000 被其他项目占用，启动脚本会显示检测到的应用标题并拒绝误判为当前项目。

## Demo 稳定模式

默认开启稳定 Demo 模式：

```env
DEMO_SEED=20260702
DEMO_DETERMINISTIC=true
```

相同的业务名称、开始日期、结束日期、对比方式和 Demo Seed 会生成相同模拟数据，重启后仍可复现；更换业务、时间范围或 Demo Seed 会得到不同数据。模拟数据只用于作品集演示，不代表真实业务。

## 服务量变化占比

当前保留原计算逻辑，但对外名称统一为“服务量变化占比”：

```text
服务量变化占比 = 某因素服务量变化 / 本期整体服务量
```

该指标用于近似衡量因素变化与整体异动之间的相对关联，不代表严格因果关系，也不是精确归因值。API 新字段为 `service_change_ratio`，旧字段 `contrib_wanfu` 暂时保留用于兼容旧前端或旧接口。

## DeepSeek 降级机制

配置项：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_USE_ENV_PROXY=false
```

默认不继承系统代理，避免异常代理导致 TLS EOF。确需代理时，可设置 `HTTP_PROXY` / `HTTPS_PROXY` 并将 `DEEPSEEK_USE_ENV_PROXY=true`。

实时模型不可用时，系统仍会完成数据查询和 `anomaly_calc` 指标计算，并返回结构化降级报告。降级报告中的数字均来自程序计算结果。

独立诊断命令：

```powershell
python scripts/check_deepseek_connection.py
```

脚本会检查配置、DNS、TCP、TLS、API 鉴权和最小模型调用，API Key 只显示脱敏后四位。

## 正式作品集链接部署

项目已支持前后端同源部署：线上访问根路径 `/` 会直接打开 Agent 页面，页面会自动请求同一域名下的 `/api/chat/stream` 和 `/health`，不再写死 `localhost`。

### 方案一：GitHub Pages 静态作品集版（最稳，不需要后端）

仓库已提供 `docs/index.html` 静态演示页，并通过 `.github/workflows/pages.yml` 发布到 GitHub Pages。这个页面不调用真实 DeepSeek，不连接后端服务器，不需要 API Key，适合作为简历和自我介绍网站中的稳定公开链接。

启用方式：

1. 打开 GitHub 仓库的 `Settings` -> `Pages`。
2. 将 `Build and deployment` 的 `Source` 选择为 `GitHub Actions`。
3. 回到 `Actions`，运行或等待 `Deploy static portfolio demo to GitHub Pages`。
4. 部署成功后访问：

```text
https://csijia020-wq.github.io/voc-experience-anomaly-agent/
```

页面会模拟 Agent 的核心链路：用户输入、意图识别、数据查询、异动计算、报告生成和最终报告展示。完整后端版仍保留在仓库中，可本地运行或后续部署到云端。

### 方案二：Hugging Face Spaces（不需要绑卡，但依赖平台账号状态）

推荐创建 Docker 类型 Space：

1. 打开 Hugging Face，进入 `Spaces` -> `Create new Space`。
2. Space name 填：

```text
voc-experience-anomaly-agent
```

3. License 可选 `MIT`。
4. SDK 选择 `Docker`。
5. Visibility 可先选 `Public`，方便面试官直接访问。
6. 创建后进入 Space 的 `Settings` -> `Repository secrets`，手动新增：

```env
DEEPSEEK_API_KEY=你的真实 DeepSeek Key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
DEMO_SEED=20260702
DEMO_DETERMINISTIC=true
DEEPSEEK_USE_ENV_PROXY=false
LLM_CONNECT_TIMEOUT_SECONDS=10
LLM_READ_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=1
```

不要把真实 Key 写入代码、README、Dockerfile 或 GitHub。

7. 将本仓库内容推送到 Hugging Face Space 仓库。Space 会读取根目录的 `Dockerfile`，启动命令为：

```text
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}
```

8. 部署完成后，打开 Hugging Face 提供的地址，例如：

```text
https://huggingface.co/spaces/你的用户名/voc-experience-anomaly-agent
```

这个地址就是可以放进自我介绍网站、简历或作品集的正式演示链接。免费 Space 可能会休眠，首次打开需要等待启动；启动后即可正常输入问题并生成报告。

### 方案三：Render Web Service（需要账号验证）

如果可以接受 Render 的账号验证，也可以使用 Render Web Service 生成长期作品集链接：

1. 将本仓库推送到 GitHub。
2. 在 Render 中选择 `New` -> `Blueprint`，连接仓库 `voc-experience-anomaly-agent`。
3. Render 会读取根目录的 `render.yaml`，自动使用：

```text
buildCommand: pip install -r backend/requirements.txt
startCommand: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

4. 在 Render 服务的 Environment 中手动新增：

```env
DEEPSEEK_API_KEY=你的真实 DeepSeek Key
```

不要把真实 Key 写入代码、README 或 `render.yaml`。

5. 部署完成后，打开 Render 提供的地址，例如：

```text
https://voc-experience-anomaly-agent.onrender.com/
```

这个地址就是可以放进自我介绍网站、简历或作品集的正式演示链接。Render 免费实例可能会有冷启动，首次打开需要等待几十秒；冷启动后即可正常输入问题并生成报告。

## 固定演示问题

```text
生成到餐客服上周周报
```

稳定核心指标示例：

- 本期万服：120.47
- 对比期万服：126.72
- 同比：-4.94%
- 服务量：92568
- 订单量：7684020
- Top 推高因素：华南战区，服务量变化占比 0.48%
- Top 压低因素：退款进度，服务量变化占比 -0.04%
