# 体验异动分析报告生成（experience-anomaly-report）

## 架构说明

本模块采用**两阶段架构**：
- **第一阶段（确定性工具执行）**: 调用 `anomaly_calc` 工具完成所有数学计算（含口径自校验）
- **第二阶段（LLM 解读）**: 基于计算结果生成文字报告

**禁止行为**: LLM 禁止自行计算任何数值，禁止补数、编造外部原因，必须引用计算结果。

---

## 固定 6 个分析维度（字段名）

| 序号 | 维度 | 字段名 |
|---|---|---|
| 1 | 城市等级 | `city_level` |
| 2 | 事件类别 | `event_category` |
| 3 | 六级 FAQ | `faq_level_6` |
| 4 | 一级门店品类 | `store_category_level_1` |
| 5 | 进线渠道 | `incoming_channel` |
| 6 | 一级战区 | `warzone_level_1` |

> 6 维度为并列独立拆解维度；不同维度存在重复归因，不跨维度简单加总。

## 统一指标口径

```text
万服 = 服务量 ÷ 订单量 × 10000

服务量变化占比
=（维度项本期服务量 − 维度项对比期服务量）÷ 本期整体服务量 × 100%

万服波动贡献（次/万单）
= 维度项本期服务量 ÷ 本期整体订单量 × 10000
− 维度项对比期服务量 ÷ 对比期整体订单量 × 10000
```

**排序规则**：归因 Top 按 `wanfu_contribution`（万服波动贡献）排序；正值推高，负值压低。
`service_change_ratio`（服务量变化占比）只用于辅助说明服务量规模变化，不等同于万服贡献，
不能用于替代归因排序，不能写成「贡献了万服变化」。

## 工具定义

### anomaly_calc

**描述**: 体验异动分析核心确定性计算工具。

**参数**:
```json
{
  "current_data": "本期明细数据（来自 query_friday_data）",
  "compare_data": "对比期明细数据",
  "daily_current": "本期日粒度数据",
  "daily_compare": "对比期日粒度数据",
  "dimension_availability": {
    "city_level": true,
    "event_category": true,
    "faq_level_6": true,
    "store_category_level_1": true,
    "incoming_channel": true,
    "warzone_level_1": true
  },
  "overall_base": "独立整体基数（本期/对比期 total_service 与 total_order）"
}
```

**计算任务**:
1. 整体万服 YoY 计算
2. 各维度 delta / YoY% / 服务量变化占比 / 万服波动贡献
3. 每个维度自动计算波动贡献度 Top3（推高/压低）
4. 异动打标
5. 日趋势数组生成
6. 各维度明细汇总表
7. 数据口径自校验（两期订单量基数对比，超范围阻断）

**返回格式**（标准字段 `dimensions`，旧字段 `dim` 兼容保留）:
```json
{
  "overall": {
    "current": 10.00,
    "compare": 8.66,
    "yoy": 15.57,
    "delta": 1.35,
    "service_cnt": 113411,
    "order_cnt": 113379057,
    "service_yoy": 11.1,
    "order_yoy": -3.9
  },
  "dimensions": {
    "city_level": [
      {"name": "B", "curr_service": 20775, "prev_service": 17016, "delta": 3759,
       "yoy": 22.1, "service_change_ratio": 0.03, "wanfu_contribution": 0.32}
    ],
    "event_category": [],
    "faq_level_6": [],
    "store_category_level_1": [],
    "incoming_channel": [],
    "warzone_level_1": []
  },
  "dimension_tops": {
    "city_level": {"top_up": [], "top_down": []}
  },
  "daily_trend": [],
  "alerts": [],
  "dimension_availability": {}
}
```

---

## 异动打标规则

| 标签 | 条件 | 说明 |
|-----|------|------|
| `new_added` | 本期有数据，上期无 | 新增维度项 |
| `disappeared` | 上期有数据，本期无 | 消失维度项 |
| `new_actual` | 上期<10且本期>100 | 近零增长，非口径问题 |
| `extreme_value` | \|YoY\|>500%且上期≥10 | 疑似口径调整 |

---

## LLM 报告生成规范（第二阶段）

收到 `anomaly_calc` 输出的 JSON 后，按以下 **固定 5 个模块** 顺序生成报告：

1. **核心指标** — 本期/对比期万服、服务量、订单量及同比变化
2. **综合结论** — 整体变化方向、主要推高因素、主要压低因素及注意事项
3. **日度趋势** — 本期与对比期日万服趋势及异常日期
4. **6 维度拆解** — 逐维度展示主要波动项、变化方向和业务解释
5. **明细与告警** — 维度明细、不可用维度、新增/消失项、极端值和口径风险

> 报告视觉组件（指标卡片、进度条、趋势图、明细表等）数量不作为报告模块计数口径。

## 禁止行为
- ❌ 禁止自行计算 YoY% / 服务量变化占比 / 万服波动贡献
- ❌ 禁止修改 calc 输出的数字，禁止补数
- ❌ 禁止对 available=false 的维度编造数据
- ❌ 禁止遗漏任何模块
- ❌ 禁止用「导致 / 证明」等确定因果措辞，应使用「关联 / 可能反映 / 建议关注」
- ❌ 禁止用 service_change_ratio 替代 wanfu_contribution 做归因排序
