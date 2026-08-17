"""SSE 流程说明文案构建器。

注意：这里的文案是「流程说明」（process narration），用于在前端流式展示当前
执行到哪一个确定性环节，而不是真实 LLM 的推理过程。真实推理只发生在两个节点：
1) 入口意图识别（LLM 优先，规则降级）；2) 报告文字生成（LLM 仅基于计算结果写文案）。
其余取数、口径自校验、异动计算、HTML 生成均由后端确定性工作流完成。
外部分发与归档能力本轮不落地（仅保留本地 HTML 报告生成）。
"""

from typing import Any, Dict


def build_intent_thinking(business: str, period: str) -> str:
    return (
        f"[流程说明] 已完成意图识别：业务={business}，周期={period}。"
        "接下来由后端确定性工作流按固定顺序执行：参数校验 → 数据查询 → 口径自校验 "
        "→ 异动计算 → 报告生成 → HTML 生成。"
    )


def build_parameter_validation_thinking(business: str, period: str) -> str:
    return (
        f"[流程说明] 参数校验通过：业务范围「{business}」、周期「{period}」均为有效参数。"
        "缺失或不支持的参数会在此阶段被阻断，不会静默使用默认值。"
    )


def build_data_query_thinking(business: str, period: str) -> str:
    return (
        f"[流程说明] 调用 friday-mcp 查询「{business}」在「{period}」的本期与对比期数据："
        "周粒度明细 + 日粒度趋势，覆盖 6 个标准维度（城市等级 / 事件类别 / 六级FAQ / "
        "一级门店品类 / 进线渠道 / 一级战区）。"
    )


def build_calibration_thinking() -> str:
    return (
        "[流程说明] 数据口径自校验：对比两期订单量基数，万服强制走「服务量 ÷ 订单量 × 10000」口径。"
        "若两期订单量基数差异超出合理范围，将暂停报告生成并提示用户确认，不会自动下结论。"
    )


def build_anomaly_calc_thinking(overall: Dict[str, Any] = None, calc_result: Dict[str, Any] = None) -> str:
    if not overall:
        return (
            "[流程说明] 进入确定性异动计算（experience-anomaly-report）："
            "1) 整体万服（服务量 ÷ 订单量 × 10000）；"
            "2) 各维度万服波动贡献与服务量变化占比（两个指标独立保存、独立展示，归因排序只用万服波动贡献）；"
            "3) 每个维度自动计算 Top3 推高/压低项；4) 日度趋势；5) 异动打标与告警。"
        )

    calc_result = calc_result or {}
    detail = calc_result.get("dimensions") or calc_result.get("dim", {}).get("detail", {})
    dim_count = len([k for k, v in detail.items() if v])
    return (
        f"[流程说明] 确定性计算完成：本期万服 {overall.get('current', 0)}，"
        f"对比期 {overall.get('compare', 0)}，同比 {overall.get('yoy', 0)}%。"
        f"共拆解 {dim_count} 个可用维度。所有数字均由程序计算，非模型生成。"
    )


def build_report_generation_thinking() -> str:
    return (
        "[流程说明] 进入报告生成：LLM 仅基于上游结构化计算结果撰写文字，"
        "不得重算、补数或编造外部原因。报告按固定 5 模块组织：核心指标 / 综合结论 / "
        "日度趋势 / 6 维度拆解 / 明细与告警。"
    )


def build_html_generation_thinking() -> str:
    return (
        "[流程说明] HTML 生成：基于确定性计算结果渲染本地 5 模块可视化报告（s3plus-upload 本地落地，"
        "返回本地 file:// 链接，非真实 S3 上传）。外部分发与归档为后续可接入能力，本轮不落地。"
    )
