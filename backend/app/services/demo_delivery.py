"""本地 HTML 报告生成（s3plus-upload 的本地落地）。

只负责把确定性计算结果渲染为本地 5 模块 HTML 报告文件，返回本地 file:// 链接。
不接真实 S3、不上传 CDN，不触发大象分发（dx-api-tools-bai）或学城同步（meituan-km + kmedit）。
"""

from __future__ import annotations

import html
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

STANDARD_DIMENSIONS = (
    "city_level",
    "event_category",
    "faq_level_6",
    "store_category_level_1",
    "incoming_channel",
    "warzone_level_1",
)

DEFAULT_DIMENSION_LABELS = {
    "city_level": "城市等级",
    "event_category": "事件类别",
    "faq_level_6": "六级FAQ",
    "store_category_level_1": "一级门店品类",
    "incoming_channel": "进线渠道",
    "warzone_level_1": "一级战区",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_output_dir() -> Path:
    return _project_root() / "output"


def _safe_timestamp(timestamp: Optional[str] = None) -> str:
    return timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_error(output_dir: Path, message: str) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir / "demo_mock_errors.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} {message}\n")
    except Exception:
        logger.warning("Demo Mock side-effect failed: %s", message)


def _safe_text(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _format_number(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "0.00"


def _format_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _format_ratio(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def _summary_to_html(summary: Any) -> str:
    escaped = _safe_text(summary)
    lines = [line.strip() for line in escaped.splitlines()]
    paragraphs = [line for line in lines if line and not line.startswith("#")]
    return "<p>" + "<br>".join(paragraphs or [escaped]) + "</p>"


def build_five_modules_data(
    business: str,
    period: str,
    calc_result: Dict[str, Any],
    report_prompt: str,
    summary: str,
) -> Dict[str, Any]:
    return {
        "title": f"{business} {period} 体验异动分析报告",
        "business": business,
        "period": period,
        "summary": summary,
        "report_prompt": report_prompt,
        "calc_result": calc_result,
        "dimension_labels": DEFAULT_DIMENSION_LABELS,
    }


def render_html_report(modules_data: Dict[str, Any]) -> str:
    """Render the fixed five-module visual report.

    为什么报告生成必须依赖于已经计算好的 modules_data，而不能让 HTML 渲染器
    自己去算一遍指标？因为万服、万服波动贡献、同比和告警都必须来自同一套
    确定性计算链路。渲染器只负责展示已经计算好的结构化结果，避免展示层二次
    计算造成数据口径漂移，确保“显示即计算结果”。
    """

    def to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    modules_data = modules_data or {}
    calc_result = (
        modules_data.get("calc_result")
        or modules_data.get("analysis_result")
        or {}
    )
    overall = calc_result.get("overall") or {}
    dim_result = calc_result.get("dim") or {}
    detail = dim_result.get("detail") or calc_result.get("dimensions") or {}
    daily_trend = calc_result.get("daily_trend") or []
    alerts = calc_result.get("alerts") or []
    availability = calc_result.get("dimension_availability") or {}
    labels = {**DEFAULT_DIMENSION_LABELS, **(modules_data.get("dimension_labels") or {})}

    has_data = bool(overall or detail or daily_trend)
    title = modules_data.get("title") or "体验异动分析报告"
    business = modules_data.get("business") or ""
    period = modules_data.get("period") or ""
    yoy = to_float(overall.get("yoy", 0))
    yoy_class = "metric-up" if yoy > 0 else "metric-down" if yoy < 0 else "metric-flat"
    trend_word = "上升" if yoy > 0 else "下降" if yoy < 0 else "持平"

    top_up = list(dim_result.get("top_up") or [])
    top_down = list(dim_result.get("top_down") or [])
    top_up_text = _safe_text(top_up[0].get("name", "")) if top_up else "暂无明显推高项"
    top_down_text = _safe_text(top_down[0].get("name", "")) if top_down else "暂无明显压低项"
    if has_data:
        deterministic_summary = (
            f"本期万服为 {_format_number(overall.get('current', 0))}，"
            f"对比期万服为 {_format_number(overall.get('compare', 0))}，"
            f"整体变化率 {_format_number(yoy)}%，呈{trend_word}趋势。"
            f"本期服务量 {_format_int(overall.get('service_cnt', 0))}，"
            f"订单量 {_format_int(overall.get('order_cnt', 0))}。"
            f"主要推高项为 {top_up_text}，主要压低项为 {top_down_text}。"
        )
    else:
        deterministic_summary = "暂无数据，当前页面仅保留报告仪表盘框架。"

    alert_items = "".join(
        f"<li><strong>{_safe_text(item.get('name', item.get('type', '告警')))}</strong>"
        f"<span>{_safe_text(item.get('desc', ''))}</span></li>"
        for item in alerts
    )
    alert_box = (
        f'<div class="alert-box"><h3>告警提示</h3><ul>{alert_items}</ul></div>'
        if alerts else ""
    )
    summary_panel_class = "summary-panel has-alerts" if alerts else "summary-panel"

    trend_labels: List[str] = []
    current_series: List[float] = []
    compare_series: List[float] = []
    trend_is_simulated = not bool(daily_trend)
    if daily_trend:
        for item in daily_trend[:7]:
            trend_labels.append(str(item.get("date", "")))
            current_series.append(to_float(item.get("current_wanfu", item.get("curr_wanfu", 0))))
            compare_series.append(to_float(item.get("compare_wanfu", item.get("prev_wanfu", 0))))
    else:
        base_current = to_float(overall.get("current", 126.78), 126.78)
        base_compare = to_float(overall.get("compare", 131.75), 131.75)
        trend_labels = ["D-6", "D-5", "D-4", "D-3", "D-2", "D-1", "D"]
        offsets = [-0.05, -0.02, 0.01, -0.01, 0.03, 0.07, 0.02]
        current_series = [round(base_current * (1 + offset), 2) for offset in offsets]
        compare_series = [round(base_compare * (1 + offset / 2), 2) for offset in reversed(offsets)]

    max_current = max(current_series) if current_series else 0
    anomaly_flags = [
        bool(max_current and value == max_current)
        for value in current_series
    ]
    fallback_items = "".join(
        f"<li><span>{_safe_text(label)}</span>"
        f"<strong>本期 {_format_number(curr)} / 对比期 {_format_number(prev)}</strong></li>"
        for label, curr, prev in zip(trend_labels, current_series, compare_series)
    )
    chart_config = {
        "labels": trend_labels,
        "current": current_series,
        "compare": compare_series,
        "anomalyFlags": anomaly_flags,
    }

    dimension_sections: List[str] = []
    table_rows: List[str] = []
    for dim_key in STANDARD_DIMENSIONS:
        items = list(detail.get(dim_key, []))
        label = labels.get(dim_key, dim_key)
        contribution_threshold = 0.5
        positive_candidates = sorted(
            [
                item for item in items
                if to_float(item.get("wanfu_contribution", item.get("contrib_wanfu", 0))) > 0
            ],
            key=lambda item: to_float(item.get("wanfu_contribution", item.get("contrib_wanfu", 0))),
            reverse=True,
        )[:2]
        negative_candidates = sorted(
            [
                item for item in items
                if to_float(item.get("wanfu_contribution", item.get("contrib_wanfu", 0))) < 0
            ],
            key=lambda item: to_float(item.get("wanfu_contribution", item.get("contrib_wanfu", 0))),
        )[:2]

        def render_impact_items(group: List[Dict[str, Any]], value_class: str) -> str:
            if not group:
                return '<li class="impact-empty">无显著波动</li>'

            visible_group = [
                item for item in group
                if abs(to_float(item.get("wanfu_contribution", item.get("contrib_wanfu", 0)))) >= contribution_threshold
            ]
            if not visible_group:
                return '<li class="impact-empty">波动幅度极小，建议关注其他维度。</li>'

            rows: List[str] = []
            for item in visible_group:
                contribution = to_float(item.get("wanfu_contribution", item.get("contrib_wanfu", 0)))
                sign = "+" if contribution > 0 else ""
                item_text = f"{item.get('name', '')} ({sign}{_format_number(contribution)} 次/万单)"
                rows.append(
                    f"""
                    <li class="dimension-impact-item" title="{_safe_text(item_text)}" aria-label="{_safe_text(item_text)}">
                      <span class="impact-name">{_safe_text(item.get('name', ''))}</span>
                      <strong class="impact-value {value_class}">({sign}{_format_number(contribution)} 次/万单)</strong>
                    </li>
                    """
                )
            return "".join(rows)

        positive_items = [
            item for item in positive_candidates
            if abs(to_float(item.get("wanfu_contribution", item.get("contrib_wanfu", 0)))) >= contribution_threshold
        ]
        negative_items = [
            item for item in negative_candidates
            if abs(to_float(item.get("wanfu_contribution", item.get("contrib_wanfu", 0)))) >= contribution_threshold
        ]
        positive_html = render_impact_items(positive_candidates, "bar-positive-text")
        negative_html = render_impact_items(negative_candidates, "bar-negative-text")
        impact_count = len(positive_items) + len(negative_items)
        badge_text = f"{impact_count}项" if impact_count else "无波动"

        dimension_sections.append(
            f"""
            <section class="dimension-card" data-dimension="{_safe_text(dim_key)}">
              <div class="dimension-title">
                <div>
                  <h3>{_safe_text(label)}</h3>
                  <p>{_safe_text(dim_key)}</p>
                </div>
                <span>{_safe_text(badge_text)}</span>
              </div>
              <div class="dimension-split">
                <div class="dimension-column positive-column">
                  <h4>🔺 主要推高</h4>
                  <ul>{positive_html}</ul>
                </div>
                <div class="dimension-column negative-column">
                  <h4>🔻 主要压降</h4>
                  <ul>{negative_html}</ul>
                </div>
              </div>
            </section>
            """
        )

        for item in items:
            table_rows.append(
                f"""
                <tr>
                  <td>{_safe_text(label)}</td>
                  <td>{_safe_text(item.get('name', ''))}</td>
                  <td>{_format_int(item.get('curr_service', 0))}</td>
                  <td>{_format_int(item.get('prev_service', 0))}</td>
                  <td>{_format_number(item.get('wanfu_contribution', item.get('contrib_wanfu', 0)))}</td>
                  <td>{_format_ratio(item.get('service_change_ratio', 0))}</td>
                  <td>{_format_number(item.get('yoy', 0))}%</td>
                </tr>
                """
            )

    if not table_rows:
        table_rows.append(
            '<tr><td colspan="7" class="empty-table">暂无数据</td></tr>'
        )

    unavailable = [
        labels.get(dim, dim)
        for dim in STANDARD_DIMENSIONS
        if availability.get(dim) is False
    ]
    unavailable_text = "、".join(unavailable) if unavailable else "无"
    alert_detail = "".join(
        f"<li><strong>{_safe_text(item.get('type', 'alert'))}</strong>"
        f"<span>{_safe_text(item.get('name', ''))} {_safe_text(item.get('desc', ''))}</span></li>"
        for item in alerts
    ) or "<li><strong>无</strong><span>当前无告警</span></li>"
    empty_banner = (
        '<div class="empty-banner">暂无数据</div>'
        if not has_data else ""
    )
    simulated_note = (
        '<p class="data-note">*基于模拟数据生成*</p>'
        if trend_is_simulated else ""
    )

    style = """
    :root {
      --page: #f4f6f8;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #637083;
      --line: #dde3ea;
      --line-strong: #c8d1dc;
      --blue: #2563eb;
      --blue-soft: #eff6ff;
      --green: #15803d;
      --green-soft: #eaf7ef;
      --red: #dc2626;
      --red-soft: #fff1f2;
      --amber: #b45309;
      --amber-soft: #fff7ed;
      --shadow: 0 14px 34px rgba(20, 35, 60, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--page);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      line-height: 1.55;
    }
    .report-shell {
      width: min(1280px, calc(100% - 40px));
      margin: 0 auto;
      padding: 28px 0 40px;
      display: grid;
      gap: 18px;
    }
    .report-header, .report-section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .report-header {
      padding: 24px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 18px;
    }
    .report-title h1 {
      margin: 0;
      font-size: 26px;
      line-height: 1.25;
      letter-spacing: 0;
    }
    .report-title p {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 14px;
    }
    .demo-badge {
      flex: 0 0 auto;
      padding: 6px 10px;
      border: 1px solid #fed7aa;
      border-radius: 8px;
      color: var(--amber);
      background: var(--amber-soft);
      font-size: 12px;
      font-weight: 700;
    }
    .report-section { padding: 22px; }
    .section-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }
    .section-head h2 {
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }
    .section-head span {
      color: var(--muted);
      font-size: 12px;
    }
    .empty-banner {
      padding: 14px 16px;
      border: 1px dashed var(--line-strong);
      border-radius: 8px;
      background: #fbfcfd;
      color: var(--muted);
      font-weight: 700;
    }
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }
    .metric-card {
      min-height: 122px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfdff;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .metric-label {
      color: var(--muted);
      font-size: 13px;
      font-weight: 650;
    }
    .metric-value {
      display: block;
      margin-top: 14px;
      font-size: 31px;
      line-height: 1;
      font-weight: 800;
      letter-spacing: 0;
    }
    .metric-sub {
      color: var(--muted);
      font-size: 12px;
      margin-top: 10px;
    }
    .metric-up { color: var(--red); }
    .metric-down { color: var(--green); }
    .metric-flat { color: var(--blue); }
    .summary-panel {
      padding: 18px;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      background: var(--blue-soft);
      display: grid;
      gap: 14px;
    }
    .summary-panel.has-alerts {
      border: 2px dashed var(--red);
      background: #fffafa;
    }
    .summary-main {
      margin: 0;
      font-size: 15px;
      color: #263244;
    }
    .summary-extra {
      color: #475569;
      font-size: 14px;
    }
    .summary-extra p { margin: 0; }
    .alert-box {
      padding: 14px;
      border-radius: 8px;
      border: 1px solid #fecdd3;
      background: var(--red-soft);
    }
    .alert-box h3 {
      margin: 0 0 8px;
      color: #991b1b;
      font-size: 15px;
    }
    .alert-box ul, .detail-lists ul, .trend-fallback ul {
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .alert-box li {
      display: flex;
      gap: 8px;
      color: #7f1d1d;
      font-size: 13px;
    }
    .chart-panel {
      min-height: 340px;
      padding: 6px 0 0;
      position: relative;
    }
    .chart-wrap {
      height: 320px;
      width: 100%;
    }
    .data-note {
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 12px;
    }
    .trend-fallback {
      margin-top: 12px;
      padding: 12px;
      border-radius: 8px;
      border: 1px dashed var(--line-strong);
      background: #fbfcfd;
    }
    .trend-fallback[hidden] { display: none; }
    .trend-fallback li {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 6px 0;
      color: var(--muted);
      border-bottom: 1px solid #edf1f5;
    }
    .trend-fallback li:last-child { border-bottom: 0; }
    .dimensions-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .dimension-card {
      min-height: 196px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fcfdff;
    }
    .dimension-title {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 14px;
    }
    .dimension-title h3 {
      margin: 0;
      font-size: 16px;
      letter-spacing: 0;
    }
    .dimension-title p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 12px;
    }
    .dimension-title span {
      color: var(--blue);
      background: var(--blue-soft);
      border-radius: 8px;
      padding: 4px 8px;
      font-size: 12px;
      font-weight: 700;
    }
    .dimension-split {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .dimension-column {
      min-height: 126px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .dimension-column h4 {
      margin: 0;
      font-size: 14px;
      letter-spacing: 0;
    }
    .dimension-column ul {
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 8px;
    }
    .positive-column {
      border-color: #bbf7d0;
      background: var(--green-soft);
    }
    .positive-column h4 { color: var(--green); }
    .negative-column {
      border-color: #fecdd3;
      background: var(--red-soft);
    }
    .negative-column h4 { color: var(--red); }
    .dimension-impact-item {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 0;
      border-bottom: 1px solid rgba(100, 116, 139, 0.14);
      font-size: 13px;
    }
    .dimension-impact-item:last-child { border-bottom: 0; }
    .impact-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #263244;
      font-weight: 700;
    }
    .impact-value {
      flex: 0 0 auto;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
      font-weight: 800;
    }
    .impact-empty {
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 13px;
      font-style: italic;
    }
    .dimension-sort-note {
      margin: 12px 0 0;
      color: var(--muted);
      font-size: 12px;
      font-style: italic;
    }
    .dimension-bars {
      display: grid;
      gap: 10px;
    }
    .dimension-bar-row {
      display: grid;
      grid-template-columns: minmax(96px, 0.8fr) minmax(160px, 1.7fr) minmax(128px, 0.9fr);
      gap: 10px;
      align-items: center;
      font-size: 13px;
    }
    .bar-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #263244;
      font-weight: 650;
    }
    .bar-track {
      position: relative;
      height: 14px;
      background: #edf2f7;
      border-radius: 8px;
      overflow: hidden;
    }
    .bar-axis {
      position: absolute;
      left: 50%;
      top: 0;
      bottom: 0;
      width: 1px;
      background: #94a3b8;
      z-index: 2;
    }
    .bar-fill {
      position: absolute;
      top: 0;
      bottom: 0;
      border-radius: 8px;
    }
    .bar-positive { right: 50%; background: var(--green); }
    .bar-negative { left: 50%; background: var(--red); }
    .bar-positive-text { color: var(--green); }
    .bar-negative-text { color: var(--red); }
    .bar-value {
      text-align: right;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
      font-weight: 700;
    }
    .detail-table-wrap {
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .detail-table {
      width: 100%;
      min-width: 900px;
      border-collapse: collapse;
      font-size: 13px;
    }
    .detail-table th,
    .detail-table td {
      padding: 11px 12px;
      text-align: left;
      border-bottom: 1px solid var(--line);
      white-space: nowrap;
    }
    .detail-table th {
      background: #f8fafc;
      color: var(--muted);
      font-weight: 750;
    }
    .detail-table.zebra tbody tr:nth-child(even) { background: #fbfdff; }
    .detail-table tbody tr:last-child td { border-bottom: 0; }
    .empty-table, .empty-state {
      color: var(--muted);
      text-align: center;
    }
    .detail-lists {
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .detail-list-card {
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }
    .detail-list-card h3 {
      margin: 0 0 10px;
      font-size: 14px;
    }
    .detail-list-card li {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 6px 0;
      color: var(--muted);
      font-size: 13px;
    }
    @media (max-width: 980px) {
      .metrics-grid, .dimensions-grid, .detail-lists { grid-template-columns: 1fr; }
      .report-header, .section-head { flex-direction: column; align-items: flex-start; }
      .dimension-split, .dimension-bar-row { grid-template-columns: 1fr; }
      .bar-value { text-align: left; }
    }
    @media (max-width: 560px) {
      .report-shell { width: min(100% - 24px, 1280px); padding-top: 16px; }
      .report-header, .report-section { padding: 16px; }
      .metric-value { font-size: 26px; }
      .chart-wrap { height: 260px; }
    }
    """

    script = f"""
  <script>
    const trendData = {json.dumps(chart_config, ensure_ascii=False)};
    const trendFallback = document.getElementById('trendFallback');
    const ctx = document.getElementById('trendChart');
    try {{
      if (!window.Chart || !ctx) {{
        if (trendFallback) trendFallback.hidden = false;
      }} else {{
        new Chart(ctx, {{
          type: 'line',
          data: {{
            labels: trendData.labels,
            datasets: [
              {{
                label: '本期万服',
                data: trendData.current,
                borderColor: '#2563eb',
                backgroundColor: 'rgba(37, 99, 235, 0.12)',
                borderWidth: 3,
                tension: 0.32,
                pointRadius: trendData.anomalyFlags.map(flag => flag ? 7 : 4),
                pointHoverRadius: trendData.anomalyFlags.map(flag => flag ? 9 : 6),
                pointBackgroundColor: trendData.anomalyFlags.map(flag => flag ? '#dc2626' : '#2563eb'),
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2
              }},
              {{
                label: '对比期万服',
                data: trendData.compare,
                borderColor: '#94a3b8',
                backgroundColor: 'rgba(148, 163, 184, 0.10)',
                borderDash: [7, 5],
                borderWidth: 2,
                tension: 0.32,
                pointRadius: 4,
                pointBackgroundColor: '#94a3b8'
              }}
            ]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
              legend: {{ position: 'bottom' }},
              tooltip: {{ mode: 'index', intersect: false }}
            }},
            interaction: {{ mode: 'nearest', intersect: false }},
            scales: {{
              x: {{ grid: {{ display: false }} }},
              y: {{ beginAtZero: false, grid: {{ color: '#edf2f7' }} }}
            }}
          }}
        }});
      }}
    }} catch (error) {{
      if (trendFallback) trendFallback.hidden = false;
    }}
  </script>
"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_safe_text(title)}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>{style}</style>
</head>
<body>
  <main class="report-shell">
    <header class="report-header">
      <div class="report-title">
        <h1>{_safe_text(title)}</h1>
        <p>{_safe_text(business)} {_safe_text(period)} · Demo Mock 本地可视化渲染，非真实生产环境发布。</p>
        <p class="data-note">本项目使用模拟数据，仅用于作品集演示，不代表真实生产数据或真实业务结果。</p>
      </div>
      <span class="demo-badge">Demo Mock</span>
    </header>
    {empty_banner}

    <section class="report-section" id="module-core-metrics">
      <div class="section-head"><h2>模块 1：核心指标</h2><span>由 anomaly_calc 确定性计算</span></div>
      <div class="metrics-grid">
        <article class="metric-card"><span class="metric-label">本期万服</span><strong class="metric-value">{_format_number(overall.get('current', 0))}</strong><span class="metric-sub">服务量 / 订单量 * 10000</span></article>
        <article class="metric-card"><span class="metric-label">对比期万服</span><strong class="metric-value">{_format_number(overall.get('compare', 0))}</strong><span class="metric-sub">同口径对比周期</span></article>
        <article class="metric-card"><span class="metric-label">变化率</span><strong class="metric-value {yoy_class}">{_format_number(yoy)}%</strong><span class="metric-sub">红涨绿跌</span></article>
        <article class="metric-card"><span class="metric-label">总服务量</span><strong class="metric-value">{_format_int(overall.get('service_cnt', 0))}</strong><span class="metric-sub">订单量 {_format_int(overall.get('order_cnt', 0))}</span></article>
      </div>
    </section>

    <section class="report-section" id="module-summary">
      <div class="section-head"><h2>模块 2：综合结论</h2><span>基于 overall 与 alerts 生成</span></div>
      <div class="{summary_panel_class}">
        <p class="summary-main">{deterministic_summary}</p>
        {alert_box}
      </div>
    </section>

    <section class="report-section" id="module-daily-trend">
      <div class="section-head"><h2>模块 3：日度趋势</h2><span>本期 vs 对比期</span></div>
      <div class="chart-panel">
        <div class="chart-wrap"><canvas id="trendChart"></canvas></div>
        {simulated_note}
        <div id="trendFallback" class="trend-fallback" hidden>
          <strong>Chart.js 未加载，以下为趋势数据降级展示</strong>
          <ul>{fallback_items}</ul>
        </div>
      </div>
    </section>

    <section class="report-section" id="module-dimensions">
      <div class="section-head"><h2>模块 4：6维度拆解</h2><span>按 wanfu_contribution 绝对值排序</span></div>
      <div class="dimensions-grid">{''.join(dimension_sections)}</div>
      <p class="dimension-sort-note">*按万服波动贡献排序（正值=推高，负值=压降）*</p>
    </section>

    <section class="report-section" id="module-alerts-detail">
      <div class="section-head"><h2>模块 5：明细与告警</h2><span>维度明细表</span></div>
      <div class="detail-table-wrap">
        <table class="detail-table zebra">
          <thead><tr><th>维度</th><th>维度项</th><th>本期服务量</th><th>对比期服务量</th><th>wanfu_contribution</th><th>service_change_ratio</th><th>YoY</th></tr></thead>
          <tbody>{''.join(table_rows)}</tbody>
        </table>
      </div>
      <p class="data-note">指标说明：<strong>wanfu_contribution（万服波动贡献，次/万单）</strong>用于归因排序，解释该维度项推高或压低整体万服的绝对贡献；<strong>service_change_ratio（服务量变化占比）</strong>仅辅助说明服务量规模变化。两者独立保存、独立展示，不回退、不混用；不同维度存在重复归因，不跨维度加总。</p>
      <div class="detail-lists">
        <div class="detail-list-card">
          <h3>不可用维度</h3>
          <ul><li><strong>{_safe_text(unavailable_text)}</strong><span>维度可用性</span></li></ul>
        </div>
        <div class="detail-list-card">
          <h3>告警列表</h3>
          <ul>{alert_detail}</ul>
        </div>
      </div>
    </section>
  </main>
{script}</body>
</html>
"""


def mock_s3plus_upload(
    business: str,
    period: str,
    calc_result: Dict[str, Any],
    report_prompt: str,
    summary: str,
    output_dir: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, str]:
    # 本地 HTML 报告生成（s3plus-upload 的本地落地）。不接真实 S3，不上传 CDN。
    target_dir = Path(output_dir) if output_dir else _default_output_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_ts = _safe_timestamp(timestamp)
    report_path = target_dir / f"report_{safe_ts}.html"

    modules_data = build_five_modules_data(
        business=business,
        period=period,
        calc_result=calc_result,
        report_prompt=report_prompt,
        summary=summary,
    )
    try:
        html_content = render_html_report(modules_data)
    except Exception as exc:
        error_text = f"Demo Mock HTML report render failed: {type(exc).__name__}: {exc}"
        logger.warning(error_text)
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Demo Mock 渲染失败</title>
  <style>
    body {{
      margin: 0;
      background: #f4f6f8;
      color: #172033;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    }}
    .error-shell {{
      width: min(760px, calc(100% - 40px));
      margin: 56px auto;
      padding: 22px;
      border: 1px solid #fecdd3;
      border-radius: 8px;
      background: #fffafa;
      box-shadow: 0 14px 34px rgba(20, 35, 60, 0.08);
    }}
    .error-shell h1 {{ margin: 0 0 12px; font-size: 22px; }}
    .error-shell p {{ margin: 8px 0; line-height: 1.6; }}
    .error-message {{
      margin-top: 14px;
      padding: 12px;
      border-radius: 8px;
      background: #fff1f2;
      color: #991b1b;
      word-break: break-word;
    }}
  </style>
</head>
<body>
  <main class="error-shell">
    <h1>Demo Mock HTML 渲染失败</h1>
    <p>非真实生产环境 API 调用。主报告生成不应被此旁路失败阻断。</p>
    <div class="error-message">{html.escape(error_text)}</div>
  </main>
</body>
</html>
"""
    report_path.write_text(html_content, encoding="utf-8")
    return {
        "report_path": str(report_path),
        "report_url": report_path.resolve().as_uri(),
        "report_filename": report_path.name,
    }


def run_local_html_report_delivery(
    business: str,
    period: str,
    calc_result: Dict[str, Any],
    report_prompt: str,
    summary: str,
    output_dir: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """本地 HTML 报告生成（s3plus-upload 的本地落地，非真实 S3 上传）。

    本轮只落地「本地 HTML 报告生成」。大象分发（dx-api-tools-bai）与学城
    归档（meituan-km + kmedit）均为后续可接入能力，不在当前主链路中落地，
    此处不再包含任何分发日志或知识库归档逻辑。
    """
    target_dir = Path(output_dir) if output_dir else _default_output_dir()
    safe_ts = _safe_timestamp(timestamp)
    result: Dict[str, Any] = {
        "demo_mock": True,
        "report_url": "",
        "report_path": "",
        "errors": [],
    }

    try:
        upload = mock_s3plus_upload(
            business=business,
            period=period,
            calc_result=calc_result,
            report_prompt=report_prompt,
            summary=summary,
            output_dir=str(target_dir),
            timestamp=safe_ts,
        )
        result.update(upload)
    except Exception as exc:
        message = f"mock_s3plus_upload failed: {type(exc).__name__}: {exc}"
        result["errors"].append(message)
        _write_error(target_dir, message)

    return result


def retry_local_html_report_delivery(
    business: str,
    period: str,
    calc_result: Dict[str, Any],
    report_prompt: str,
    summary: str,
    output_dir: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """从失败节点重试本地 HTML 生成（Demo Mock）。

    复用已保存的 calc_result / summary，不重新取数、不重新计算，
    只重新渲染并生成本地 HTML。
    """
    return run_local_html_report_delivery(
        business=business,
        period=period,
        calc_result=calc_result,
        report_prompt=report_prompt,
        summary=summary,
        output_dir=output_dir,
        timestamp=timestamp,
    )
