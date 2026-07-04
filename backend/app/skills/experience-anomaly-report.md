# 体验异动分析报告生成

## 架构说明

本模块采用**两阶段架构**：
- **第一阶段（工具执行）**: 调用 `anomaly_calc` 工具完成数学计算
- **第二阶段（LLM解读）**: 基于计算结果生成文字报告

**禁止行为**: LLM禁止自行计算任何数值，必须调用工具获取数据。

---

## 工具定义

### anomaly_calc

**描述**: 体验异动分析核心计算工具

**参数**:
```json
{
  "current_data": "本期明细数据（来自query_friday_data）",
  "compare_data": "对比期明细数据",
  "daily_current": "本期日粒度数据",
  "daily_compare": "对比期日粒度数据",
  "dimension_availability": {
    "城市等级": true,
    "品类": true,
    "事件类别": true,
    "进线渠道": true,
    "战区": true,
    "FAQ": true
  }
}
```

**计算任务**:
1. 整体万服YoY计算
2. 各维度delta/YoY%/服务量变化占比
3. 异动打标
4. Top5推高/压低排序
5. 日趋势数组生成
6. 各维度明细汇总表

**返回格式**:
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
  "dim": {
    "top_up": [
      {"name": "维度值", "dim_type": "维度类型", "delta": 0.32, "yoy": 22.1, "service_change_ratio": 0.32, "contrib_wanfu": 0.32, "curr_service": 20775, "prev_service": 17016}
    ],
    "top_down": [
      {"name": "维度值", "dim_type": "维度类型", "delta": -0.03, "yoy": -4.0, "service_change_ratio": -0.03, "contrib_wanfu": -0.03}
    ],
    "detail": {
      "城市等级": [{"name": "B", "curr_service": 20775, "prev_service": 17016, "delta": 3759, "yoy": 22.1, "contrib": 0.32}],
      "品类": [...],
      "事件类别": [...],
      "进线渠道": [...],
      "战区": [...],
      "FAQ": [...]
    }
  },
  "daily_trend": [
    {"date": "周一 3/16", "curr_wanfu": 12.68, "prev_wanfu": 9.52, "yoy": 33.2, "delta": 3.16}
  ],
  "alerts": [
    {"type": "new_category", "name": "平台服务", "desc": "本期新增事件分类"},
    {"type": "extreme_value", "name": "某维度", "yoy": 666.1, "desc": "变化幅度过大"}
  ],
  "dimension_availability": {
    "城市等级": true, "品类": true, "事件类别": true, "进线渠道": true, "战区": true, "FAQ": true
  }
}
```

---

## 异动打标规则

| 标签 | 条件 | 说明 |
|-----|------|------|
| `up_major` | 服务量变化占比Top5且正向 | 主要推高因素 |
| `down_major` | 服务量变化占比Top5且负向 | 主要压低因素 |
| `new_added` | 本期有数据，上期无 | 新增维度项 |
| `disappeared` | 上期有数据，本期无 | 消失维度项 |
| `new_actual` | 上期<10且本期>100 | 近零增长，非口径问题 |
| `extreme_value` | \|YoY\|>500%且上期≥10 | 疑似口径调整 |

---

## LLM报告生成规范（第二阶段）

收到 `anomaly_calc` 输出的JSON后，按以下模块顺序生成报告：

### 模块一：核心指标面板
```
【核心指标】
- 本期人工万服：{overall.current}（{本期周次}）
- 去年同期万服：{overall.compare}（{对比期周次}）
- 万服同比：{上升/下降} {overall.yoy}%（差 {overall.delta}）
- 服务量：{service_cnt}（{+service_yoy}%，+{增量}次）
- 订单量：{order_cnt}（{order_yoy}%）
```

### 模块二：综合分析
```
【综合分析】
**总结**：{本期周次} {业务}人工万服 {overall.current}，同比{上升/下降} {overall.yoy}%。
主因为{服务量/订单量}同比{大幅增加/减少} {service_yoy}%，{订单量同比}。

**▲ 推高万服主因**
- {dim.top_up[0].name}（{dim.top_up[0].dim_type}）：{上升} {dim.top_up[0].yoy}%

**▼ 压低万服维度**
- {dim.top_down[0].name}（{dim.top_down[0].dim_type}）：{下降} {dim.top_down[0].yoy}%
```

### 模块三：日万服趋势
```
【日万服趋势】（本期 vs 去年同期）
| 日期 | 本期万服 | 去年同期 | YoY% |
|------|---------|---------|------|
{遍历daily_trend生成表格}
```

### 模块四：各维度分析
对每个维度类型（城市等级/品类/事件类别/进线渠道/战区/FAQ）生成：
- Top推高/压低项列表
- 服务量变化占比排名表

### 模块五：告警解读
```
【告警解读】
- {alert.name}：{alert.desc}
```

---

## 禁止行为
- ❌ 禁止自行计算YoY%/服务量变化占比
- ❌ 禁止修改calc输出的数字
- ❌ 禁止对available=false的维度编造数据
- ❌ 禁止遗漏任何模块
