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

推荐使用 Render Web Service 生成长期作品集链接：

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
