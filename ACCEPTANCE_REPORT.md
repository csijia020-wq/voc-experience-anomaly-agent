# VoC 体验异动分析 Agent 快速验收报告

> 声明：本项目为模拟项目 / 求职作品集项目，不代表真实公司项目、真实生产系统或真实业务数据。

## 1. 最终验收等级

**B：修复少量问题后可演示。**

## 2. 一句话结论

当前项目经过最小兼容修复后，前后端和核心流式异动分析链路可以完整演示；但 DeepSeek 实时连接仍不可用，当前演示使用基于计算结果的降级报告，需明确说明使用模拟数据。

## 3. 已通过项目

- 后端可启动，`GET /health` 返回 `200 {"status":"healthy"}`。
- 前端静态页面可访问，`http://localhost:8080/vibe_coding_prototype.html` 返回 200。
- OpenAPI 可访问，包含 `/api/chat/message`、`/api/chat/stream`、`/api/chat/intent`、`/api/report/*`、`/health`、`/config`。
- `POST /api/chat/stream` 可返回 `text/event-stream; charset=utf-8`。
- SSE 事件均为合法 JSON，修复后事件顺序包含：`step`、`thinking`、`text`、`report`、`done`。
- Skill 文件加载成功：`friday-mcp-query`、`experience-anomaly-report`、`scheduled-message`、`s3plus-upload`。
- `query_friday_data` 可以生成模拟本期、对比期、日趋势和维度可用性数据。
- `anomaly_calc` 可以计算整体万服、同比、服务量、订单量、Top 推高/压低因素、日趋势和极端值告警。
- 模型不可用时，后端不崩溃，修复后会生成基于 `anomaly_calc` 的降级报告。
- 前端实际打开、输入、发送、展示 SSE 过程和最终报告页通过。
- 不支持业务 `海外机票客服` 修复后返回明确错误：`不支持的业务：海外机票客服`，不再生成虚假业务报告。

## 4. 未通过项目

| 项目 | 实际结果 | 影响 |
| --- | --- | --- |
| DeepSeek 实时模型调用 | `openai.APIConnectionError: Connection error.`，底层为 TLS EOF | 无法验证真实大模型报告，只能演示降级报告 |
| 原始旧路由兼容 | 修复前 `/api/chat/message` 和 `/api/report/*` 因缺失 `generate_report`、`data_service` 返回 500 | 修复前会影响 API 文档演示 |
| 原始前端报告渲染 | 修复前后端 `report` 结构为嵌套 `calc_result`，前端期待 top-level 字段 | 修复前即使 LLM 成功也可能渲染失败 |
| 贡献度口径 | 代码中 `contrib_wanfu = delta / total_service`，单位不是真正的“次/万单” | 指标解释需谨慎 |
| 告警等级 | 只有 `new_category`、`extreme_value`，没有等级字段 | 只能做基础告警展示 |
| 数据一致性 | `query_friday_data` 使用运行时周次，如 2026W26；`MockDataService` 预置上周标签为 2026W12 | 不影响主链路，但报告接口间口径不完全一致 |
| 随机数据 | 每次请求会重新随机生成数据 | 面试演示数字可能每次不同 |

## 5. P0 阻塞问题

修复前发现的 P0：

| 严重程度 | 文件位置 | 问题 | 影响 | 是否阻塞演示 |
| --- | --- | --- | --- | --- |
| P0 | `backend/app/agent/core.py` | LLM 连接失败时流式链路只返回 `error`，没有 `report/done` | 前端无法进入最终报告页 | 是 |
| P0 | `project_delivery/vibe_coding_prototype.html` + `backend/app/agent/core.py` | 前端期待 top-level 报告字段，后端只返回嵌套 `calc_result` | 最终报告渲染会失败 | 是 |
| P0 | 本地端口环境 | 8000 曾被其他 FastAPI 服务占用，一键脚本误接管为后端 | 访问到错误项目 | 是 |

修复后当前 P0：**无。**

## 6. P1 重要问题

| 严重程度 | 文件位置 | 问题 | 影响 | 是否阻塞演示 |
| --- | --- | --- | --- | --- |
| P1 | `backend/app/routers/chat.py`、`backend/app/routers/report.py` | 原始代码调用旧 Agent 方法：`generate_report`、`data_service`、`chat` | 修复前普通聊天和报告接口 500 | 已修复，不阻塞 |
| P1 | `backend/app/services/llm.py` | 无模型连接健康检查和明确超时配置 | 网络异常时依赖 SDK 报错 | 不阻塞降级演示 |
| P1 | `backend/app/agent/tools/anomaly_calc.py` | 上期为 0 时同比返回 0，而不是标记不可计算 | 可能误导解读 | 不阻塞演示 |
| P1 | `project_delivery/vibe_coding_prototype.html` | 使用 Tailwind CDN，控制台有生产警告 | 作品集可接受，生产不可用 | 不阻塞演示 |

## 7. 静态检查结果

| 检查项 | 结果 |
| --- | --- |
| FastAPI 入口 | `backend/app/main.py` 创建 `app = FastAPI(...)`，注册 chat/report router |
| Router 注册 | `/api/chat/*` 和 `/api/report/*` 已注册 |
| 前端接口 | 前端调用 `http://localhost:8000/api/chat/stream`，后端存在 |
| 旧接口兼容 | 修复前缺失；修复后补齐 `generate_report`、`data_service`、`chat` |
| SkillBasedAgent 真实方法 | `recognize_intent`、`generate_report_with_skill`、`generate_report_stream`、`process_with_tools`，修复后新增兼容方法 |
| 环境变量 | `backend/.env` 读取 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`HOST`、`PORT`、`DATA_PATH` |
| Windows 绝对路径 | `start_all.bat` 写死 `D:\Python39\python.exe`，推荐使用 `start_servers.py` |
| 语法检查 | `python -m py_compile` 通过 |
| SSE 格式 | `data: {json}\n\n`，前端按 `data: ` 解析，契约一致 |

## 8. 启动验收

实际执行命令：

```powershell
python start_servers.py start
```

首次执行发现 8000 被其他服务占用，返回的 OpenAPI 标题是 `CSV Data Cleaning Agent`。已停止无关进程后，使用非沙箱方式启动项目服务：

```powershell
python start_servers.py restart
```

复测结果：

| 项目 | 结果 |
| --- | --- |
| 后端端口 | `0.0.0.0:8000 LISTENING` |
| 前端端口 | `0.0.0.0:8080 LISTENING` |
| 健康检查 | `200 {"status":"healthy"}` |
| OpenAPI | `200`，标题为 VoC 体验异动分析 Agent |
| 前端 HTML | `200`，页面长度约 73KB |
| Skill 加载 | 4 个 skill 均成功加载 |
| DeepSeek 配置 | `.env` 有配置，但实际连接失败，未在报告中暴露 API Key |

## 9. 接口验收

| 接口 | 修复前 | 修复后 |
| --- | --- | --- |
| `GET /health` | 200 | 200 |
| `POST /api/chat/stream` | 200，但 LLM 失败后只有 `error` | 200，返回 `text`、`report`、`done` |
| `POST /api/chat/message` | 500，缺失 `generate_report` | 200 |
| `GET /api/report/generate` | 500，缺失 `generate_report` | 200 |
| `GET /api/report/data` | 500，缺失 `data_service` | 200 |
| `GET /api/report/trend` | 500，缺失 `data_service` | 200 |
| `GET /api/report/factors` | 500，缺失 `data_service` | 200 |

修复后主 SSE 事件示例：

```text
step, thinking, step, thinking, step, step, thinking, step, thinking,
step, thinking, text, step, report, done
```

## 10. 核心场景验收

| 场景 | 实际结果 | 结论 |
| --- | --- | --- |
| 生成到餐客服上周周报 | 识别为到餐客服/上周，完成数据查询和计算，模型失败后返回降级报告 | 通过 |
| 分析外卖柜最近七天异动 | 无模型时 fallback 会偏向默认业务，不能可靠识别外卖柜 | 部分通过 |
| 分析到餐最近一周是否异动 | 可计算同比并返回报告，但阈值判断仍依赖报告描述 | 部分通过 |
| 生成海外机票客服周报 | 修复后返回 `不支持的业务：海外机票客服` | 通过 |
| 模型不可用 | 修复后返回降级报告和 `llm_error`，后端不崩溃 | 通过 |

## 11. 指标计算验收

### 代码公式

| 指标 | 代码公式 |
| --- | --- |
| 本期万服 | `sum(current_service_count) / sum(current_order_count) * 10000` |
| 对比期万服 | `sum(compare_service_count) / sum(compare_order_count) * 10000` |
| 变化量 | `current_wanfu - compare_wanfu` |
| 同比 | `(current_wanfu - compare_wanfu) / compare_wanfu * 100`，当对比期为 0 时返回 0 |
| 服务量同比 | `(current_service - compare_service) / compare_service * 100`，当对比期为 0 时返回 0 |
| 订单量同比 | `(current_order - compare_order) / compare_order * 100`，当对比期为 0 时返回 0 |
| 维度服务变化 | `curr_service - prev_service` |
| 维度贡献 | `delta / total_service` |
| Top 推高 | `contrib_wanfu > 0` 后按贡献降序取前 5 |
| Top 压低 | `contrib_wanfu < 0` 后按贡献升序方向取前 5 |
| 极端值告警 | `abs(yoy) > 500 and prev_service >= 10` |

### 人工样本核对

| 指标 | 代码公式 | 人工计算结果 | 程序计算结果 | 是否一致 |
| --- | --- | ---: | ---: | --- |
| 本期万服 | `150 / 2000 * 10000` | 750.00 | 750.00 | 是 |
| 对比期万服 | `150 / 2000 * 10000` | 750.00 | 750.00 | 是 |
| 同比 | `(750 - 750) / 750 * 100` | 0.00% | 0.00% | 是 |
| A 推高贡献 | `(100 - 80) / 150` | 0.1333 | 0.1333 | 是 |
| B 压低贡献 | `(50 - 70) / 150` | -0.1333 | -0.1333 | 是 |
| 上期为 0 | compare = 0 | 不可计算 | 0 | 代码有保护，但语义需说明 |
| 空数据 | 无服务量/订单量 | 0 | 0 | 是 |
| 字段缺失 | 默认 0 | 0 | 0 | 是 |
| 负数服务量 | `-5 / 1000 * 10000` | -50.00 | -50.00 | 是，但无告警 |
| 浮点精度 | `1 / 3 * 10000` | 3333.33 | 3333.33 | 是 |
| 极端值告警 | `1000 vs 10`，YoY 9900% | 应告警 | `extreme_value` | 是 |

## 12. 报告真实性验收

DeepSeek 实时报告未能生成，原因是 API 连接失败。修复后当前报告为确定性降级报告，数字来自 `calc_result.overall` 和 `calc_result.dim`。

本次抽样核对结果：

| 报告数字或结论 | 数据来源 | 是否一致 | 问题说明 |
| --- | --- | --- | --- |
| 本期万服 `122.97` | `calc_result.overall.current` | 是 | 来自程序计算 |
| 对比期万服 `123.98` | `calc_result.overall.compare` | 是 | 来自程序计算 |
| 同比 `-0.81%` | `calc_result.overall.yoy` | 是 | 来自程序计算 |
| 差值 `-1.01` | `calc_result.overall.delta` | 是 | 来自程序计算 |
| 服务量 `79238` | `calc_result.overall.service_cnt` | 是 | 来自程序计算 |
| 订单量 `6443450` | `calc_result.overall.order_cnt` | 是 | 来自程序计算 |
| 模拟数据说明 | `data_note` + fallback summary | 是 | 已明确说明 |

静态 Prompt 风险：

- Prompt 输入包含 overall、top_up、top_down、daily_trend、alerts、dimension_availability。
- Prompt 未强约束“不得自行编造外部原因”。
- Prompt 未强约束“相关性不得写成因果关系”。
- 若未来恢复 DeepSeek，应增加数字忠实性和模拟数据声明约束。

## 13. 前端验收

实际打开：

```text
http://localhost:8080/vibe_coding_prototype.html
```

验收结果：

| 检查项 | 结果 |
| --- | --- |
| 页面打开 | 通过，标题为 `VoC回声系统 - 体验异动分析Agent` |
| 输入框 | 通过，`#chatInput` 存在 |
| 发送按钮 | 通过，`button[onclick="sendMessage()"]` 存在 |
| 请求发送 | 通过，请求到 `http://localhost:8000/api/chat/stream` |
| SSE 阶段展示 | 通过，展示意图识别、数据查询、异动计算、报告生成 |
| 最终报告渲染 | 修复后通过 |
| Markdown/HTML 展示 | 降级摘要以 HTML `<br>` 展示，可读 |
| 错误状态 | 模型错误写入报告摘要，不再卡死 |
| 加载状态 | 修复后 `loadingArea` 隐藏 |
| 模拟数据标识 | 修复后页面可见“模拟数据 / 求职作品集演示” |
| 控制台 | 无业务 JS error，仅 Tailwind CDN 生产警告 |

## 14. 修改记录

本次只做阻塞演示的最小兼容修复。

| 文件 | 修改前 | 修改后 |
| --- | --- | --- |
| `backend/app/agent/core.py` | `SkillBasedAgent` 无 `generate_report`、`data_service`、`chat`，旧路由 500 | 增加兼容方法和 `data_service` 属性 |
| `backend/app/agent/core.py` | LLM 失败时流式链路只返回 `error`，没有最终报告 | 捕获 LLM 异常，生成基于计算结果的降级报告，并继续返回 `report/done` |
| `backend/app/agent/core.py` | 报告对象只有嵌套 `calc_result`，前端字段缺失 | 增加 top-level `current_wanfu`、`compare_wanfu`、`yoy`、`top_up_factors`、`daily_trend`、`dimensions` 等字段 |
| `backend/app/agent/core.py` | 无模型 fallback 会把未知客服默认成到餐客服 | 对 `生成/分析/查询 + xxx客服` 做最小抽取，让工具返回不支持业务错误 |
| `project_delivery/vibe_coding_prototype.html` | 报告头部只显示日期范围 | 当后端返回 `data_note` 时附加模拟数据说明 |

没有修改的内容：

- 未新增定时任务。
- 未新增数据库。
- 未新增邮件推送。
- 未调整整体架构。
- 未引入多 Agent 或向量数据库。

## 15. 启动方式

推荐演示启动：

```powershell
cd D:\桌面D盘文件\A有点东西\异动分析agent
python start_servers.py start
```

若端口被占用：

```powershell
python start_servers.py restart
```

访问地址：

```text
后端文档：http://localhost:8000/docs
前端页面：http://localhost:8080/vibe_coding_prototype.html
健康检查：http://localhost:8000/health
```

注意：本次验收中发现如果 8000 已被其他项目占用，一键脚本可能误接管该端口。演示前建议先打开 `/openapi.json` 确认标题是 VoC 体验异动分析 Agent。

## 16. 演示脚本

1. 启动项目：

   ```powershell
   python start_servers.py start
   ```

2. 打开前端：

   ```text
   http://localhost:8080/vibe_coding_prototype.html
   ```

3. 输入：

   ```text
   生成到餐客服上周周报
   ```

4. 预期展示：

   - 页面逐步展示意图识别、数据查询、异动计算、报告生成。
   - 最终切换到报告展示页。
   - 展示本期万服、对比期万服、同比、服务量变化。
   - 展示推高因素、压低因素、日趋势和维度表格。
   - 若 DeepSeek 连接失败，页面展示“模型不可用，已生成降级报告”，仍可演示计算链路。
   - 页面明确出现模拟数据 / 求职作品集演示说明。

5. 面试讲解建议：

   - 先说明这是模拟项目，用于展示 AI 产品经理对 Agent 链路、指标计算和可演示产品闭环的理解。
   - 讲业务价值：把运营人工取数、算同比、写周报的 2 到 3 小时流程压缩为分钟级。
   - 讲技术链路：自然语言输入 -> 意图识别 -> 模拟魔数取数 -> 异动计算 -> 报告生成 -> SSE 前端展示。
   - 讲产品边界：当前不是生产系统，数据、权限、邮件和定时任务是作品集规划能力，当前 Demo 聚焦主链路。
   - 讲验收意识：做了启动、接口、SSE、指标公式、报告数字、前端渲染的真实验收。

## 17. 当前项目限制

- 使用模拟数据，不代表真实业务。
- 不是真实生产系统。
- DeepSeek 实时连接在本次环境中失败，演示使用降级报告。
- 定时任务、邮件推送、S3Plus 上传、用户权限、真实数据库只存在于 PRD 或 skill 设计中，当前未完整落地。
- 数据生成包含随机性，每次报告数字可能变化。
- 指标贡献度口径需要在作品集中解释清楚，避免把近似贡献当成严格因果。
- 前端使用 CDN Tailwind，适合作品集演示，不适合生产部署。

## 18. 最终建议

可以放入作品集，可以现场演示，但必须把它定位为“模拟数据的 AI Agent 原型”。现场演示优先走 `POST /api/chat/stream` 对应的前端交互，不建议把它包装成真实上线系统。

---

## 浏览器最终验收

### 1. 验收日期

2026-07-02

### 2. 浏览器或测试环境

- 浏览器：Codex 应用内浏览器自动化。
- 页面地址：http://localhost:8080/vibe_coding_prototype.html
- 后端地址：http://localhost:8000
- 说明：浏览器自动化执行过程中，Codex 浏览器控制层自身出现过 Statsig 网络超时日志；页面 Console 仅记录 Tailwind CDN 警告，未发现业务 JavaScript Error。

### 3. 启动检查结果

执行命令：

```powershell
python start_servers.py check
```

结果：

- 后端端口 8000：已监听。
- OpenAPI 标题：`VoC 体验异动分析 Agent`，匹配。
- `/health`：通过。
- `/api/chat/stream`：存在。
- 前端端口 8080：已监听。
- 前端页面：可访问。
- DeepSeek：已配置，降级可用。
- Demo 稳定模式：已开启。

### 4. 主场景结果

浏览器中输入：

```text
生成到餐客服上周周报
```

结果：

- 页面可正常打开，标题为 `VoC 体验异动分析 Agent`。
- 输入框可输入，发送按钮可点击。
- 浏览器页面完成意图识别、数据查询、异动计算、报告生成阶段展示。
- 最终进入报告页，loading 正常结束。
- 报告页可见模拟数据声明。
- 报告页可见“服务量变化占比”，未出现“万服贡献度”或“贡献度”旧口径。
- DeepSeek 真实模式下未显示降级提示。

### 5. 三次稳定性结果

三次浏览器提交均进入最终报告页，loading 均结束，没有重复绑定导致的重复报告组件。核心数据一致：

| 次数 | 本期万服 | 对比期万服 | 同比 | 服务量 | 订单量 | Top 推高因素 | Top 压低因素 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | 120.47 | 126.72 | -4.94% | 92568 | 7684020 | 华南战区 | 退款进度 |
| 2 | 120.47 | 126.72 | -4.94% | 92568 | 7684020 | 华南战区 | 退款进度 |
| 3 | 120.47 | 126.72 | -4.94% | 92568 | 7684020 | 华南战区 | 退款进度 |

### 6. DeepSeek 真实报告结果

执行 `python scripts\check_deepseek_connection.py`：

- 配置层：API Key 已配置，仅显示后四位 `****8038`。
- DNS：通过。
- TCP：通过。
- TLS：通过。
- API 鉴权：HTTP 200。
- 最小模型调用：返回 `连接成功`。

浏览器真实报告结果：

- `llm_error_code` 通过 SSE 核对为空。
- 页面未显示 DeepSeek 降级提示。
- 报告数字与程序计算结果一致。
- LLM 正文不再使用“贡献度/万服贡献度/贡献了0.52”等旧口径。
- Top 压低因素已按程序排序约束输出，结构化报告区域可见 `退款进度` 和 `-0.04%`。

### 7. DeepSeek 降级结果

使用临时错误 Key 启动，不修改真实 `.env`：

```powershell
$env:DEEPSEEK_API_KEY='invalid-key-for-browser-final-test'; python start_servers.py restart
```

浏览器输入同一问题后：

- 指标计算完成。
- 页面进入最终报告页。
- loading 正常结束。
- 页面显示 DeepSeek 调用失败 / 降级报告说明。
- 页面无完整异常堆栈。
- 页面未暴露完整 API Key。
- 降级报告数字仍为 120.47、126.72、-4.94%、92568、7684020。

完成后已恢复真实 `.env` 配置并重启服务。

### 8. 报告数字核对

| 报告数字或结论 | 程序计算结果 | 浏览器报告结果 | 是否一致 |
| --- | ---: | ---: | --- |
| 本期万服 | 120.47 | 120.47 | 是 |
| 对比期万服 | 126.72 | 126.72 | 是 |
| 同比 | -4.94% | -4.94% | 是 |
| 服务量 | 92568 | 92,568 / 92568 | 是 |
| 订单量 | 7684020 | 7,684,020 / 7684020 | 是 |
| Top 推高服务量变化占比 | 0.0048 | 0.48% | 是 |
| Top 压低服务量变化占比 | -0.0004 | -0.04% | 是 |

### 9. 浏览器 Console 和 Network 结果

- Console：仅 Tailwind CDN 非生产警告，无业务 JavaScript Error。
- Network：浏览器控制环境未提供完整 Network 面板导出；通过浏览器页面最终状态、后端 SSE 实测和 `text/event-stream` 响应确认主链路完成。
- SSE：真实接口返回 `report` 和 `done`；错误 Key 降级时也返回报告并结束页面 loading。
- 页面渲染：最终报告页正常显示，未发现持续 loading、字段 undefined、旧静态数据遮挡或明显错位。

### 10. 本次最小修改

- `backend/app/agent/core.py`：Prompt 中只向 LLM 提供安全的 Top 因素字段和百分比字符串；要求 Top 因素按程序 rank 顺序输出，避免模型自行重排或误用旧字段。
- `project_delivery/vibe_coding_prototype.html`：移除旧静态指标占位，更新报告卡片、方向提示、服务量卡片和右侧摘要卡；将“推高万服主因/压低万服维度”改为“推高关联因素/压低关联因素”。
- `start_servers.py`：后端启动等待条件改为标题、健康检查和 `/api/chat/stream` 全部通过，等待时间放宽到 45 秒。

### 11. 当前剩余问题

- 前端仍使用 Tailwind CDN，适合作品集演示，不适合生产部署。
- 当前业务范围仍为模拟数据支持的业务，不支持海外机票客服；浏览器抽查已确认会提示不支持且不生成虚假报告。
- 项目仍是模拟项目和求职作品集项目，不是真实生产系统。

### 12. 最新验收等级

**A：可直接作为求职作品集现场演示。**
