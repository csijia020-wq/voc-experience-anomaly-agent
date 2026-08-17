"""
Agent核心逻辑 - 基于Skill架构的实现

整合skill文件定义的工具和工作流
"""
from typing import Dict, Any, List, Optional, AsyncGenerator
import json
import asyncio
import logging
import re

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm import LLMServiceError, llm_service
from app.services.demo_delivery import run_local_html_report_delivery, retry_local_html_report_delivery
from app.services.scheduled_tasks import scheduled_task_store
from app.agent.task_state import TaskStatus, task_store
from app.agent.tools.anomaly_calc import anomaly_calc, ANOMALY_CALC_TOOL
from app.agent.tools.query_friday_data import query_friday_data, QUERY_FRIDAY_TOOL
from app.agent.prompts.intent import build_intent_messages
from app.agent.prompts.planning import (
    build_anomaly_calc_thinking,
    build_calibration_thinking,
    build_data_query_thinking,
    build_html_generation_thinking,
    build_intent_thinking,
    build_parameter_validation_thinking,
    build_report_generation_thinking,
)
from app.agent.prompts.report import (
    DIMENSION_DISPLAY_NAMES,
    build_report_prompt as prompt_build_report_prompt,
    format_factors_for_prompt,
    format_ratio_percent,
)
from app.skills.loader import skill_loader

# 从tools.py导入execute_tool和TOOLS_DEFINITION
import importlib.util
spec = importlib.util.spec_from_file_location("tools_module", os.path.join(os.path.dirname(__file__), "tools.py"))
tools_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools_module)
execute_tool = tools_module.execute_tool
TOOLS_DEFINITION = tools_module.TOOLS_DEFINITION

logger = logging.getLogger(__name__)

# 模块级：待确认的定时任务（Demo Mock，内存暂存，不持久化）
_pending_schedules: Dict[str, Dict[str, Any]] = {}
_pending_schedule_counter = [0]


def _new_confirm_token() -> str:
    _pending_schedule_counter[0] += 1
    return f"confirm_{_pending_schedule_counter[0]}"


def has_pending_schedule() -> bool:
    """是否存在待确认的定时任务（供路由层判断确认类回复）。

    注意：请从与 analysis_agent 相同的模块导入路径调用本函数，
    避免 agent.core 与 app.agent.core 双加载导致 _pending_schedules 引用不一致。
    """
    return bool(_pending_schedules)


class SkillBasedAgent:
    """基于Skill架构的体验异动分析Agent"""

    def __init__(self):
        self.llm = llm_service
        self.skills = {
            "friday-mcp-query": skill_loader.load_skill("friday-mcp-query"),
            "experience-anomaly-report": skill_loader.load_skill("experience-anomaly-report"),
            "scheduled-message": skill_loader.load_skill("scheduled-message"),
            "s3plus-upload": skill_loader.load_skill("s3plus-upload")
        }

    def recognize_intent(self, user_input: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
        """
        识别用户意图（LLM 优先，规则降级，符合文档 4.3 的 LLM 四大职责设计）。

        支持多轮澄清：当当前输入缺少 business / period 时，从 history 中继承
        最近一次明确过的槽位（不静默默认）。LLM 失败时降级到规则匹配。

        Args:
            user_input: 用户输入
            history: 历史消息（可选），用于槽位继承

        Returns:
            意图识别结果（含 needs_clarification 与 llm_response 字段）
        """
        if not user_input or user_input.strip() == "":
            base = {
                "intent": "generate_report",
                "business": "",
                "period": "",
                "business_source": "missing",
                "period_source": "missing",
                "comparison_type": "yoy",
                "granularity": "weekly",
                "schedule_cron": "",
                "schedule_name": "",
                "receiver": "",
                "needs_clarification": True,
                "llm_response": "请补充要分析的业务范围和对比周期，例如：到餐客服 上周。",
                "unsupported_reason": "",
                "confidence": 0.0,
            }
            return self._inherit_slots_from_history(base, history)

        # 构建带 skill 上下文的意图识别 prompt
        skill_context = self.skills.get("friday-mcp-query", "")
        messages = build_intent_messages(user_input, skill_context, history)

        # 默认优先调用 LLM
        normalized: Optional[Dict[str, Any]] = None
        try:
            parsed = self.llm.chat_json(messages, temperature=0.3)
            normalized = self._normalize_intent_result(parsed, user_input)

            # LLM 未声明缺参，但关键槽位 business / period 仍缺失，视为解析不完整，降级到规则匹配
            if not normalized.get("needs_clarification") and (
                not normalized.get("business") or not normalized.get("period")
            ):
                logger.warning(
                    "LLM 意图解析缺少关键槽位(business=%r, period=%r)，降级到规则匹配。input=%r",
                    normalized.get("business"), normalized.get("period"), user_input,
                )
                normalized = self._parse_intent_fallback(user_input)
        except LLMServiceError as e:
            logger.warning("LLM 意图识别调用失败(%s)，降级到规则匹配。input=%r", e.code, user_input)
            normalized = self._parse_intent_fallback(user_input)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning("LLM 意图解析结果非法(%s)，降级到规则匹配。input=%r", type(e).__name__, user_input)
            normalized = self._parse_intent_fallback(user_input)
        except Exception as e:
            logger.warning("LLM 意图识别异常(%s)，降级到规则匹配。input=%r", type(e).__name__, user_input)
            normalized = self._parse_intent_fallback(user_input)

        # 统一做多轮澄清槽位继承（当前输入缺槽位时，从历史补全，不静默默认）
        return self._inherit_slots_from_history(normalized, history)

    @staticmethod
    def _parse_explicit_week_period(text: str) -> Optional[str]:
        """解析用户显式指定的ISO年周，返回标准 YYYYWww。"""
        patterns = [
            r'(?<!\d)(\d{4})\s*年?\s*[Ww]\s*0*(\d{1,2})(?!\d)',
            r'(?<!\d)(\d{4})\s*[-/]\s*[Ww]\s*0*(\d{1,2})(?!\d)',
            r'(?<!\d)(\d{4})\s*年?\s*第\s*0*(\d{1,2})\s*周',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                year = int(match.group(1))
                week = int(match.group(2))
                if 1 <= week <= 53:
                    return f"{year}W{week:02d}"
        return None

    @staticmethod
    def _supported_businesses() -> List[str]:
        return ["到餐客服", "闪购客服", "企客业务"]

    @staticmethod
    def _is_valid_period(period: str) -> bool:
        """校验周期是否为受支持的格式（上周/本周/上月/本月/YYYYWww/YYYY-MM）。"""
        if not period:
            return False
        if period in ("上周", "本周", "上月", "本月"):
            return True
        if re.fullmatch(r"\d{4}W\d{2}", period):
            return True
        if re.fullmatch(r"\d{4}-\d{2}", period):
            return True
        return False

    def _normalize_intent_result(self, result: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """统一 LLM 和规则解析的意图结构，保留旧字段兼容。

        LLM 优先，规则降级，符合文档 4.3 的 LLM 四大职责设计。
        缺 business / period 时不再静默填默认值，而是置 needs_clarification=True
        并生成追问文案，交由路由层发起追问、阻断下游。
        """
        if not isinstance(result, dict):
            result = {}

        allowed_intents = {"generate_report", "query_data", "schedule_task", "chat"}
        intent = result.get("intent") or "generate_report"
        if intent not in allowed_intents:
            report_keywords = ["报告", "周报", "月报", "分析", "生成", "提取", "复盘", "异动", "指标"]
            intent = "generate_report" if any(kw in user_input for kw in report_keywords) else "chat"

        business = result.get("business") or ""
        period = result.get("period") or ""

        # LLM 未识别出业务、但输入中明显含「XX客服」等业务字样时，规则提取，
        # 以便对「海外机票客服」等不支持业务给出明确拒绝，而不是静默追问缺业务。
        if not business:
            extracted_business = self._extract_business(user_input)
            if extracted_business:
                business = extracted_business
            else:
                unsupported_match = re.search(
                    r'([^，。,.\\s]{1,12}?客服)',
                    user_input
                )
                if unsupported_match:
                    business = unsupported_match.group(1)

        # 兼容文档 4.3.2 的 current_period / compare_period 槽位命名，归一为 period
        if not period:
            current_period = result.get("current_period")
            if isinstance(current_period, dict):
                period = current_period.get("label") or \
                    f"{current_period.get('start_date', '')}~{current_period.get('end_date', '')}".strip("~")
            elif isinstance(current_period, str):
                period = current_period

        explicit_period = self._parse_explicit_week_period(str(period)) if period else None
        if explicit_period:
            period = explicit_period

        needs_clarification = bool(result.get("needs_clarification", False))
        llm_response = result.get("llm_response") or ""
        if needs_clarification and not llm_response:
            llm_response = self._build_clarification_question(user_input, business, period)

        normalized = {
            "intent": intent,
            "business": business,
            "business_source": result.get("business_source") or ("explicit_user_input" if business else "missing"),
            "period": period,
            "period_source": result.get("period_source") or ("explicit_user_input" if period else "missing"),
            "comparison_type": result.get("comparison_type") or "yoy",
            "granularity": result.get("granularity") or "weekly",
            "schedule_cron": result.get("schedule_cron") or "",
            "schedule_name": result.get("schedule_name") or "",
            "receiver": result.get("receiver") or "",
            "needs_clarification": needs_clarification,
            "llm_response": llm_response,
            "unsupported_reason": result.get("unsupported_reason") or "",
            "confidence": float(result.get("confidence", 0.7) or 0.7),
        }

        if business and business not in self._supported_businesses():
            normalized["unsupported_reason"] = f"当前项目不支持业务：{business}"

        return normalized

    @staticmethod
    def _build_clarification_question(user_input: str, business: str, period: str) -> str:
        """根据缺失槽位生成自然语言追问文案（与规格文档多轮澄清示例对齐）。

        - 缺业务：先问业务范围
        - 缺周期：再问分析周期
        - 都缺：先问业务（一次只问一项，便于多轮澄清）
        """
        if not business:
            return "请补充业务范围，例如：到餐客服 / 闪购客服 / 企客业务。"
        if not period:
            return f"请补充分析周期，例如：上周 / 本周 / 上月 / 本月 / 2026W02 / 2026-03。"
        return "请补充必要的分析参数后再试。"

    @staticmethod
    def _extract_business(text: str) -> str:
        """从文本中规则提取业务名（用于多轮澄清的历史槽位继承）。"""
        if not text:
            return ""
        business_keywords = {
            "到餐": "到餐客服",
            "餐饮": "到餐客服",
            "餐客服": "到餐客服",
            "闪购": "闪购客服",
            "即时零售": "闪购客服",
            "企客": "企客业务",
            "企业客户": "企客业务",
        }
        for keyword, business in business_keywords.items():
            if keyword in text:
                return business
        return ""

    @staticmethod
    def _extract_period(text: str) -> str:
        """从文本中规则提取周期（用于多轮澄清的历史槽位继承）。"""
        if not text:
            return ""
        week = SkillBasedAgent._parse_explicit_week_period(text)
        if week:
            return week
        period_keywords = {
            "上周": "上周",
            "本周": "本周",
            "最近七天": "本周",
            "最近一周": "本周",
            "上月": "上月",
            "本月": "本月",
        }
        for keyword, period in period_keywords.items():
            if keyword in text:
                return period
        year_month_match = re.search(r'(\d{4})[\s年/\-]?(\d{1,2})', text)
        if year_month_match:
            year, month = year_month_match.groups()
            return f"{year}-{month.zfill(2)}"
        return ""

    @staticmethod
    def _extract_cron(text: str) -> str:
        """从自然语言提取 cron 表达式（分 时 日 月 周）。"""
        minute = "0"
        hour = "9"
        weekday = "*"
        time_match = re.search(r'(\d{1,2})[:：](\d{1,2})', text)
        if time_match:
            hour = time_match.group(1)
            minute = time_match.group(2)
        else:
            point_match = re.search(r'(\d{1,2})\s*点', text)
            if point_match:
                hour = point_match.group(1)
        # 下午/晚上/中午 → 24 小时制
        if any(k in text for k in ("下午", "晚上", "中午")) and hour.isdigit():
            hour_num = int(hour)
            if hour_num < 12:
                hour = str(hour_num + 12)
        week_map = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "日": "0", "天": "0"}
        week_match = re.search(r'每周([一二三四五六日天])', text)
        if week_match:
            weekday = week_map[week_match.group(1)]
        elif "每天" in text or "每日" in text:
            weekday = "*"
        return f"{minute} {hour} * * {weekday}"

    def _inherit_slots_from_history(
        self,
        result: Dict[str, Any],
        history: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """多轮澄清：当前输入缺 business/period 时，从历史消息继承最近一次明确的槽位。

        不静默默认任何值；只在历史里确实出现过时继承。继承后重新计算
        needs_clarification 与 llm_response。
        """
        if not result:
            result = {}
        business = result.get("business") or ""
        period = result.get("period") or ""

        if history and (not business or not period):
            for item in reversed(history):
                if business and period:
                    break
                if isinstance(item, dict):
                    role = item.get("role", "user")
                    content = item.get("content", "")
                else:
                    role = getattr(item, "role", "user")
                    content = getattr(item, "content", "")
                if role != "user":
                    continue
                content = str(content or "").strip()
                if not content:
                    continue
                if not business:
                    inherited = self._extract_business(content)
                    if inherited:
                        business = inherited
                        result["business"] = inherited
                        result["business_source"] = "inherited_from_history"
                if not period:
                    inherited = self._extract_period(content)
                    if inherited:
                        period = inherited
                        result["period"] = inherited
                        result["period_source"] = "inherited_from_history"

        # 重新计算缺参追问
        if result.get("intent") == "schedule_task":
            # schedule_task 只要求业务（周期用 period_rule 默认「上一完整自然周」）
            if business:
                result["needs_clarification"] = False
                if result.get("llm_response") and "补充" in str(result.get("llm_response", "")):
                    result["llm_response"] = ""
            else:
                result["needs_clarification"] = True
                result["llm_response"] = "请补充定时任务要分析的业务范围，例如：到餐客服 / 闪购客服 / 企客业务。"
        elif business and period and not self._is_valid_period(period):
            # 周期格式非法：不得静默默认，进入澄清追问
            result["needs_clarification"] = True
            result["llm_response"] = (
                f"暂不支持周期「{period}」，请补充受支持的周期格式，例如：上周 / 本周 / 上月 / 本月 / 2026W02 / 2026-03。"
            )
        elif business and period:
            result["needs_clarification"] = False
            if result.get("llm_response") and "补充" in str(result.get("llm_response", "")):
                result["llm_response"] = ""
        else:
            result["needs_clarification"] = True
            result["llm_response"] = self._build_clarification_question("", business, period)
        return result

    def _parse_intent_fallback(self, user_input: str) -> Dict[str, Any]:
        """备用意图解析（LLM 不可用/解析失败时的降级，不删除）。

        LLM 优先，规则降级，符合文档 4.3 的 LLM 四大职责设计。
        缺 business / period 时同样置 needs_clarification=True，由 _normalize_intent_result 统一生成追问。
        """
        result = {
            "intent": "generate_report",
            "business": "",
            "period": "",
            "business_source": "",
            "period_source": "",
            "comparison_type": "yoy",
            "granularity": "weekly",
            "schedule_cron": "",
            "schedule_name": "",
            "receiver": "",
            "needs_clarification": False,
            "llm_response": "",
            "unsupported_reason": "",
            "confidence": 0.6
        }

        # 业务识别
        business_keywords = {
            "到餐": "到餐客服",
            "餐饮": "到餐客服",
            "餐客服": "到餐客服",
            "闪购": "闪购客服",
            "即时零售": "闪购客服",
            "企客": "企客业务",
            "企业客户": "企客业务",
        }
        matched_business = False
        for keyword, business in business_keywords.items():
            if keyword in user_input:
                result["business"] = business
                result["business_source"] = "explicit_user_input"
                matched_business = True
                break

        if not matched_business:
            unsupported_match = re.search(
                r'(?:生成|分析|查询|查一下|查下|提取|拉一下|出一份|复盘|看看|看下|帮我(?:做|看|提取)?)([^，。,.\\s]*?客服)',
                user_input
            )
            if unsupported_match:
                result["business"] = unsupported_match.group(1)
                result["business_source"] = "explicit_user_input"

        # 周期识别：显式年周优先，避免“2026年W2”被默认成上周。
        explicit_week_period = self._parse_explicit_week_period(user_input)
        if explicit_week_period:
            result["period"] = explicit_week_period
            result["period_source"] = "explicit_user_input"
            result["confidence"] = min(result["confidence"] + 0.2, 1.0)
        else:
            period_keywords = {
                "上周": "上周",
                "本周": "本周",
                "最近七天": "本周",
                "最近一周": "本周",
                "上月": "上月",
                "本月": "本月"
            }
            for keyword, period in period_keywords.items():
                if keyword in user_input:
                    result["period"] = period
                    result["period_source"] = "explicit_user_input"
                    break

            # YYYY-MM格式
            if not result["period"]:
                year_month_match = re.search(r'(\d{4})[\s年/\-]?(\d{1,2})', user_input)
                if year_month_match:
                    year, month = year_month_match.groups()
                    result["period"] = f"{year}-{month.zfill(2)}"
                    result["period_source"] = "explicit_user_input"
                    result["confidence"] = min(result["confidence"] + 0.2, 1.0)

        # 意图类型
        schedule_keywords = ["定时", "提醒", "计划", "每周", "每天", "自动发送"]
        report_keywords = ["报告", "周报", "月报", "分析", "异动", "生成", "提取", "拉一下", "出一份", "帮我做", "帮我看", "看下", "看看", "复盘", "指标"]
        query_keywords = ["查询", "查一下", "查下", "查", "数据"]

        if any(kw in user_input for kw in schedule_keywords):
            result["intent"] = "schedule_task"
            result["schedule_cron"] = self._extract_cron(user_input)
            result["schedule_name"] = f"{result['business']}周报" if result.get("business") else ""
            result["receiver"] = "本地 Demo"
        elif any(kw in user_input for kw in query_keywords) and not any(kw in user_input for kw in report_keywords):
            result["intent"] = "query_data"
        else:
            result["intent"] = "generate_report"

        # 缺参追问：规则降级同样严禁使用默认值，缺 business/period 时置 needs_clarification。
        # schedule_task 只要求业务（周期用 period_rule 默认「上一完整自然周」）。
        if result["intent"] == "schedule_task":
            if not result["business"]:
                result["needs_clarification"] = True
                result["llm_response"] = "请补充定时任务要分析的业务范围，例如：到餐客服 / 闪购客服 / 企客业务。"
        else:
            if not result["business"] or not result["period"]:
                result["needs_clarification"] = True
                result["llm_response"] = self._build_clarification_question(
                    user_input, result["business"], result["period"]
                )

        return self._normalize_intent_result(result, user_input)

    def generate_report_with_skill(
        self,
        business: str,
        period: str
    ) -> Dict[str, Any]:
        """
        基于Skill架构生成报告

        Args:
            business: 业务名称
            period: 时间周期

        Returns:
            报告结果
        """
        # 读取skill内容
        friday_skill = self.skills.get("friday-mcp-query", "")
        report_skill = self.skills.get("experience-anomaly-report", "")

        # 步骤1：查询数据（调用query_friday_data工具）
        query_result = execute_tool("query_friday_data", {
            "business": business,
            "period": period,
            "granularity": "weekly"
        })

        if "error" in query_result:
            return {"error": f"数据查询失败: {query_result['error']}"}

        # 口径自校验：两期订单量基数差异过大时，阻断下游并追问确认（文档 3.7 / F03）
        calibration_result = query_result.get("calibration_result")
        if calibration_result and calibration_result.get("passed") is False:
            current_order = calibration_result.get("current_order", 0)
            compare_order = calibration_result.get("compare_order", 0)
            ratio = round(current_order / compare_order, 2) if compare_order else "∞"
            return {
                "error": f"两期订单量基数差异过大（比值 {ratio}），请确认对比周期是否合理，确认后重新发起。"
            }

        current_data = query_result.get("current_data", [])
        compare_data = query_result.get("compare_data", [])
        daily_current = query_result.get("daily_current", [])
        daily_compare = query_result.get("daily_compare", [])
        dimension_availability = query_result.get("dimension_availability", {})
        overall_base = query_result.get("overall", {})
        meta = query_result.get("meta", {})

        # 步骤2：异动计算（调用anomaly_calc工具）
        calc_result = execute_tool("anomaly_calc", {
            "current_data": current_data,
            "compare_data": compare_data,
            "daily_current": daily_current,
            "daily_compare": daily_compare,
            "dimension_availability": dimension_availability,
            "overall_base": overall_base
        })

        # 确定性计算失败：阻断下游，禁止生成全 0 报告（文档 4.7 / F08）
        if "error" in calc_result:
            return {"error": f"确定性计算失败：{calc_result['error']}，请检查数据后重试。"}

        # 步骤3：LLM生成报告文字（基于skill规范）
        report_prompt = self._build_report_prompt(business, period, calc_result, meta)

        messages = [
            {"role": "system", "content": "你是一个专业的体验异动分析助手。请基于计算结果生成结构化报告。"},
            {"role": "user", "content": report_prompt}
        ]

        llm_error = None
        try:
            summary = self.llm.chat(messages, temperature=0.5)
        except Exception as e:
            llm_error = getattr(e, "user_message", str(e))
            llm_error_code = getattr(e, "code", "LLM_API_ERROR")
            summary = self._build_fallback_summary(business, period, calc_result, meta, llm_error)

        html_result = self._run_local_html_report_delivery(
            business=business,
            period=period,
            calc_result=calc_result,
            report_prompt=report_prompt,
            summary=summary,
        )

        # 组装完整报告
        return self._format_report_payload(
            business,
            period,
            calc_result,
            meta,
            summary,
            llm_error,
            locals().get("llm_error_code"),
            html_result
        )

    def generate_report(self, business: str, period: str) -> Dict[str, Any]:
        """兼容旧路由的报告生成接口。"""
        return self.generate_report_with_skill(business, period)

    def chat(self, message: str, history: Optional[List[Any]] = None) -> str:
        """兼容旧路由的普通聊天接口。"""
        messages = [{"role": "system", "content": "你是一个体验异动分析助手。"}]
        for item in history or []:
            role = getattr(item, "role", None) or item.get("role", "user") if isinstance(item, dict) else "user"
            content = getattr(item, "content", None) or item.get("content", "") if isinstance(item, dict) else str(item)
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
        try:
            return self.llm.chat(messages, temperature=0.5)
        except Exception:
            return "当前大模型服务不可用。你可以先使用“生成到餐客服上周周报”查看基于模拟数据的异动计算结果。"

    def _format_report_payload(
        self,
        business: str,
        period: str,
        calc_result: Dict[str, Any],
        meta: Dict[str, Any],
        summary: str,
        llm_error: Optional[str] = None,
        llm_error_code: Optional[str] = None,
        html_result: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """整理成前端旧字段和新版结构都能消费的报告对象。"""
        overall = calc_result.get("overall", {})
        dim = calc_result.get("dim", {})
        # 标准字段优先（文档 5.7 数据契约），旧字段 dim 兼容兜底。
        detail = calc_result.get("dimensions") or dim.get("detail", {})
        dimension_tops = calc_result.get("dimension_tops", {})
        payload = {
            "task_id": task_id or "",
            "business": business,
            "period": period,
            "date_range": f"{meta.get('current_date_range', '')} vs {meta.get('compare_date_range', '')}",
            "current_wanfu": overall.get("current", 0),
            "compare_wanfu": overall.get("compare", 0),
            "yoy": overall.get("yoy", 0),
            "delta": overall.get("delta", 0),
            "service_count": overall.get("service_cnt", 0),
            "service_yoy": overall.get("service_yoy", 0),
            "order_count": overall.get("order_cnt", 0),
            "order_yoy": overall.get("order_yoy", 0),
            "top_up_factors": dim.get("top_up", []),
            "top_down_factors": dim.get("top_down", []),
            "daily_trend": self._normalize_daily_trend(calc_result.get("daily_trend", [])),
            "dimensions": self._normalize_dimensions(detail),
            "dimension_tops": dimension_tops,
            "alerts": calc_result.get("alerts", []),
            "dimension_availability": calc_result.get("dimension_availability", {}),
            "summary": summary,
            "report_url": (html_result or {}).get("report_url", ""),
            "report_filename": (html_result or {}).get("report_filename", ""),
            "report_http_path": (f"/reports/{html_result.get('report_filename', '')}" if (html_result or {}).get("report_filename") else ""),
            "html_result": html_result or {},
            "calc_result": calc_result,
            "meta": meta,
            "data_note": "本项目使用模拟数据，仅用于作品集演示，不代表真实生产数据或真实业务结果。"
        }
        if llm_error:
            payload["llm_error"] = llm_error
        if llm_error_code:
            payload["llm_error_code"] = llm_error_code
        return payload

    def _run_local_html_report_delivery(
        self,
        business: str,
        period: str,
        calc_result: Dict[str, Any],
        report_prompt: str,
        summary: str,
    ) -> Dict[str, Any]:
        """生成本地 HTML 报告（s3plus-upload 本地落地）。"""
        try:
            return run_local_html_report_delivery(
                business=business,
                period=period,
                calc_result=calc_result,
                report_prompt=report_prompt,
                summary=summary,
            )
        except Exception as exc:
            message = f"本地 HTML 报告生成失败: {type(exc).__name__}: {exc}"
            logger.warning(message)
            return {"demo_mock": True, "report_url": "", "errors": [message]}

    def _normalize_daily_trend(self, daily_trend: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把计算工具字段转换为前端图表字段。"""
        normalized = []
        for item in daily_trend:
            normalized.append({
                "date": item.get("date", ""),
                "current_wanfu": item.get("current_wanfu", item.get("curr_wanfu", 0)),
                "compare_wanfu": item.get("compare_wanfu", item.get("prev_wanfu", 0)),
                "yoy": item.get("yoy", 0),
                "delta": item.get("delta", 0)
            })
        return normalized

    def _normalize_dimensions(self, detail: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
        """把计算工具维度明细转换为前端表格字段。"""
        dimensions = {}
        for dim_type, items in detail.items():
            dimensions[dim_type] = []
            for item in items:
                service_change_ratio = item.get("service_change_ratio", 0)
                wanfu_contribution = item.get("wanfu_contribution", item.get("contrib_wanfu", 0))
                dimensions[dim_type].append({
                    "name": item.get("name", ""),
                    "current_value": item.get("curr_service", 0),
                    "compare_value": item.get("prev_service", 0),
                    "delta": item.get("delta", 0),
                    "yoy": item.get("yoy", 0),
                    "wanfu_contribution": wanfu_contribution,
                    "service_change_ratio": service_change_ratio,
                    "contribution": wanfu_contribution
                })
        return dimensions

    def _format_ratio_percent(self, value: Any) -> str:
        return format_ratio_percent(value)

    def _format_factors_for_prompt(self, factors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """只把报告需要的安全字段交给LLM，避免误用旧字段。"""
        return format_factors_for_prompt(factors)

    def _build_fallback_summary(
        self,
        business: str,
        period: str,
        calc_result: Dict[str, Any],
        meta: Dict[str, Any],
        llm_error: str
    ) -> str:
        """模型不可用时，用计算结果生成可演示的确定性摘要。"""
        overall = calc_result.get("overall", {})
        dim = calc_result.get("dim", {})
        top_up = dim.get("top_up", [])[:3]
        top_down = dim.get("top_down", [])[:3]
        up_text = "、".join([
            f"{x.get('name')}（{DIMENSION_DISPLAY_NAMES.get(x.get('dim_type'), x.get('dim_type'))}，万服波动贡献{x.get('wanfu_contribution', x.get('contrib_wanfu', 0))}次/万单，服务量变化占比{self._format_ratio_percent(x.get('service_change_ratio', 0))}）"
            for x in top_up
        ]) or "无明显推高因素"
        down_text = "、".join([
            f"{x.get('name')}（{DIMENSION_DISPLAY_NAMES.get(x.get('dim_type'), x.get('dim_type'))}，万服波动贡献{x.get('wanfu_contribution', x.get('contrib_wanfu', 0))}次/万单，服务量变化占比{self._format_ratio_percent(x.get('service_change_ratio', 0))}）"
            for x in top_down
        ]) or "无明显压低因素"
        direction = "上升" if overall.get("yoy", 0) > 0 else "下降" if overall.get("yoy", 0) < 0 else "持平"
        return {
            "summary": (
                f"【模拟数据说明】本项目使用模拟数据，仅用于作品集演示，不代表真实生产数据或真实业务结果。<br>"
                f"【核心指标】{business}{period}本期万服为{overall.get('current', 0)}，"
                f"对比期万服为{overall.get('compare', 0)}，同比{direction}{overall.get('yoy', 0)}%，"
                f"差值为{overall.get('delta', 0)}。服务量为{overall.get('service_cnt', 0)}，"
                f"订单量为{overall.get('order_cnt', 0)}。<br>"
                f"【主要推高因素】{up_text}。<br>"
                f"【主要压低因素】{down_text}。<br>"
                f"【口径说明】归因排序使用万服波动贡献；服务量变化占比仅用于辅助说明服务量规模变化，不能证明因果关系。<br>"
                f"【模型状态】DeepSeek 调用失败，当前展示的是基于 anomaly_calc 计算结果的降级报告。错误信息：{llm_error}"
            )
        }["summary"]

    def _build_report_prompt(
        self,
        business: str,
        period: str,
        calc_result: Dict[str, Any],
        meta: Dict[str, Any]
    ) -> str:
        """构建报告生成prompt"""
        return prompt_build_report_prompt(business, period, calc_result, meta)

    async def generate_report_stream(
        self,
        business: str,
        period: str,
        task_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式生成报告，携带任务状态机（task_id + 每阶段状态）。

        每个 step / error 事件都携带 task_id；失败时记录失败节点、原因与
        可重试动作（TaskStatus.FAILED）。报告链路只落地到本地 HTML 生成
        （s3plus-upload 本地落地），不包含分发、归档等外部能力。

        Args:
            business: 业务名称
            period: 时间周期
            task_id: 可选任务 ID；缺省时新建一个任务

        Yields:
            分析步骤和数据
        """
        # 创建/复用任务状态
        if not task_id:
            record = task_store.create(business, period)
            task_id = record["task_id"]

        def _step(step: str, status: str, message: str) -> Dict[str, Any]:
            return {
                "event": "step",
                "type": "step",
                "data": {"step": step, "status": status, "message": message, "task_id": task_id},
            }

        def _thinking(step: str, content: str) -> Dict[str, Any]:
            return {
                "event": "thinking",
                "type": "thinking",
                "data": {"step": step, "task_id": task_id, "content": content},
            }

        def _error(step: str, message: str, retry_action: str) -> Dict[str, Any]:
            task_store.fail(task_id, step, message, retry_action)
            return {
                "event": "error",
                "type": "error",
                "data": {"message": message, "task_id": task_id, "step": step, "retry_action": retry_action},
            }

        # 步骤1：意图识别
        task_store.update(task_id, TaskStatus.INTENT_RECOGNIZED, step="intent_recognition", message="意图识别完成")
        yield _step("intent_recognition", "completed", "意图识别完成")
        yield _thinking("intent_recognition", build_intent_thinking(business, period))

        # 步骤2：参数校验（缺参/不支持业务已在路由层阻断；此处展示有效参数）
        task_store.update(task_id, TaskStatus.PARAMETER_VALIDATED, step="parameter_validation", message=f"参数校验完成：{business} / {period}")
        yield _step("parameter_validation", "completed", f"参数校验完成：{business} / {period}")
        yield _thinking("parameter_validation", build_parameter_validation_thinking(business, period))

        # 步骤3：查询数据
        yield _step("data_query", "running", "正在查询数据...")
        yield _thinking("data_query", build_data_query_thinking(business, period))

        query_result = execute_tool("query_friday_data", {
            "business": business,
            "period": period,
            "granularity": "weekly"
        })

        if "error" in query_result:
            yield _error("data_query", query_result["error"], "请检查业务与周期后重新发起")
            return

        task_store.update(task_id, TaskStatus.DATA_QUERIED, step="data_query", message=f"数据查询完成")

        # 步骤4：口径自校验（两期订单量基数差异过大时，阻断下游并追问确认，文档 3.7 / F03）
        yield _step("calibration", "running", "正在进行口径自校验...")
        yield _thinking("calibration", build_calibration_thinking())

        calibration_result = query_result.get("calibration_result")
        if calibration_result and calibration_result.get("passed") is False:
            current_order = calibration_result.get("current_order", 0)
            compare_order = calibration_result.get("compare_order", 0)
            ratio = round(current_order / compare_order, 2) if compare_order else "∞"
            yield _error(
                "calibration",
                f"两期订单量基数差异过大（比值 {ratio}），请确认对比周期是否合理。",
                "请确认对比周期后重新发起",
            )
            return

        task_store.update(task_id, TaskStatus.CALIBRATION_CHECKED, step="calibration", message="口径自校验通过")
        yield _step("calibration", "completed", "口径自校验通过")

        current_data = query_result.get("current_data", [])
        compare_data = query_result.get("compare_data", [])
        daily_current = query_result.get("daily_current", [])
        daily_compare = query_result.get("daily_compare", [])
        dimension_availability = query_result.get("dimension_availability", {})
        overall_base = query_result.get("overall", {})
        meta = query_result.get("meta", {})

        yield _step("data_query", "completed", f"数据查询完成，本期{len(current_data)}条记录")

        # 步骤5：异动计算
        yield _step("anomaly_calc", "running", "正在计算异动指标...")
        yield _thinking("anomaly_calc", build_anomaly_calc_thinking())

        calc_result = execute_tool("anomaly_calc", {
            "current_data": current_data,
            "compare_data": compare_data,
            "daily_current": daily_current,
            "daily_compare": daily_compare,
            "dimension_availability": dimension_availability,
            "overall_base": overall_base
        })

        # 确定性计算失败：阻断下游，禁止生成全 0 报告（文档 4.7 / F08）
        if "error" in calc_result:
            yield _error("anomaly_calc", f"确定性计算失败：{calc_result['error']}", "请检查数据后重新发起")
            return

        task_store.update(task_id, TaskStatus.CALCULATED, step="anomaly_calc", message="异动计算完成")

        overall = calc_result.get("overall", {})
        yield _step("anomaly_calc", "completed", f"计算完成，万服同比{overall.get('yoy', 0)}%")
        yield _thinking("anomaly_calc", build_anomaly_calc_thinking(overall, calc_result))

        # 步骤6：生成报告
        yield _step("report_generation", "running", "正在生成分析报告...")

        report_prompt = self._build_report_prompt(business, period, calc_result, meta)

        messages = [
            {"role": "system", "content": "你是一个专业的体验异动分析助手。"},
            {"role": "user", "content": report_prompt}
        ]

        yield _thinking("report_generation", build_report_generation_thinking())

        # 流式输出
        summary_chunks = []
        llm_error = None
        llm_error_code = None
        try:
            async for chunk in self.llm.chat_stream(messages, temperature=0.5):
                summary_chunks.append(chunk)
                yield {"event": "text", "type": "text", "data": chunk}
            summary = "".join(summary_chunks)
        except Exception as e:
            llm_error = getattr(e, "user_message", str(e))
            llm_error_code = getattr(e, "code", "LLM_API_ERROR")
            summary = self._build_fallback_summary(business, period, calc_result, meta, llm_error)
            yield {"event": "text", "type": "text", "data": summary}

        task_store.update(task_id, TaskStatus.REPORT_GENERATED, step="report_generation", message="报告文字生成完成")
        yield _step(
            "report_generation",
            "completed",
            "报告生成完成" if llm_error is None else "模型不可用，已生成降级报告",
        )

        # 步骤7：HTML 生成（s3plus-upload 本地落地）
        yield _step("html_generation", "running", "正在生成本地 HTML 报告...")
        yield _thinking("html_generation", build_html_generation_thinking())

        # 保存 retry_payload，供失败时从该节点恢复（不重新取数/计算）
        task_store.update(task_id, TaskStatus.REPORT_GENERATED, step="report_generation", retry_payload={
            "calc_result": calc_result,
            "summary": summary,
            "report_prompt": report_prompt,
        })

        html_result = self._run_local_html_report_delivery(
            business=business,
            period=period,
            calc_result=calc_result,
            report_prompt=report_prompt,
            summary=summary,
        )

        if html_result.get("errors"):
            yield _error("html_generation", html_result["errors"][0], "可调用 retry 接口重新生成本地 HTML")
            return

        task_store.update(
            task_id,
            TaskStatus.HTML_GENERATED,
            step="html_generation",
            message="本地 HTML 报告生成完成",
            report_url=html_result.get("report_url", ""),
            report_path=html_result.get("report_path", ""),
        )
        yield _step("html_generation", "completed", "本地 HTML 报告生成完成")

        # 最终报告
        yield {
            "event": "report",
            "type": "report",
            "data": self._format_report_payload(
                business,
                period,
                calc_result,
                meta,
                summary,
                llm_error,
                llm_error_code,
                html_result,
                task_id,
            )
        }

        task_store.update(task_id, TaskStatus.COMPLETED, step="completed", message="分析完成")
        yield {"event": "done", "type": "done", "data": {"message": "分析完成", "task_id": task_id}}

    def process_with_tools(self, user_input: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
        """
        使用工具处理用户请求（支持多轮澄清与定时任务确认）。

        Args:
            user_input: 用户输入
            history: 历史消息（用于槽位继承）

        Returns:
            处理结果
        """
        # 识别意图（支持多轮澄清槽位继承）
        intent_result = self.recognize_intent(user_input, history)

        # 确认待创建的定时任务（用户回复「确认」等确认词），需先于缺参追问判断
        if self._is_confirmation(user_input) and _pending_schedules:
            token = list(_pending_schedules.keys())[-1]
            params = _pending_schedules.pop(token)
            task = scheduled_task_store.create(**params)
            return {
                "intent": intent_result,
                "result": {
                    "schedule_created": task,
                    "message": f"已创建定时任务「{task['name']}」（cron={task['cron']}，Demo Mock 本地配置，非真实调度）。",
                }
            }

        # 缺参追问：LLM 判定参数不完整时，阻断下游取数/计算，返回追问
        if intent_result.get("needs_clarification"):
            return {
                "intent": intent_result,
                "result": {"message": intent_result.get("llm_response") or "请补充必要的分析参数。"}
            }

        # 不支持的业务：明确拒绝，不生成虚假报告（文档：不支持的业务要明确提示）
        if intent_result.get("unsupported_reason"):
            return {
                "intent": intent_result,
                "result": {"error": intent_result["unsupported_reason"]}
            }

        intent = intent_result.get("intent", "generate_report")
        business = intent_result.get("business", "")
        period = intent_result.get("period", "")

        # 生成报告
        if intent == "generate_report":
            report = self.generate_report_with_skill(business, period)
            return {
                "intent": intent_result,
                "result": report
            }
        elif intent == "query_data":
            query_result = execute_tool("query_friday_data", {"business": business, "period": period})
            return {
                "intent": intent_result,
                "result": query_result
            }
        elif intent == "schedule_task":
            return {
                "intent": intent_result,
                "result": self._build_schedule_confirmation(intent_result)
            }
        else:
            return {
                "intent": intent_result,
                "result": {"message": "我理解了，请告诉我您想做什么？"}
            }

    @staticmethod
    def _is_confirmation(text: str) -> bool:
        """判断用户输入是否为「确认」类回复。"""
        normalized = (text or "").strip().lower()
        return normalized in {"确认", "确认创建", "好的", "好", "创建", "是的", "确定", "可以", "ok"}

    @staticmethod
    def _build_schedule_confirmation(intent_result: Dict[str, Any]) -> Dict[str, Any]:
        """为定时任务生成待确认信息（不直接创建），并暂存到内存 pending。"""
        business = intent_result.get("business", "")
        cron = intent_result.get("schedule_cron") or "0 9 * * 1"
        name = intent_result.get("schedule_name") or (f"{business}周报" if business else "")
        receiver = intent_result.get("receiver") or "本地 Demo"
        period_rule = "上一完整自然周"

        token = _new_confirm_token()
        _pending_schedules[token] = {
            "name": name,
            "business": business,
            "period_rule": period_rule,
            "cron": cron,
            "receiver": receiver,
        }
        return {
            "needs_confirmation": True,
            "confirm_token": token,
            "schedule_preview": {
                "name": name,
                "business": business,
                "period_rule": period_rule,
                "cron": cron,
                "receiver": receiver,
            },
            "message": (
                f"即将创建定时任务：{name}（业务={business}，cron={cron}，"
                f"周期={period_rule}，接收方={receiver}）。这是 Demo Mock 本地配置，非真实调度。回复「确认」以创建。"
            ),
        }

    def retry_task(self, task_id: str) -> Dict[str, Any]:
        """从失败节点恢复（Demo Mock）：保留前序产物，不重新取数/计算。"""
        record = task_store.get(task_id)
        if not record:
            return {"error": f"任务 {task_id} 不存在"}
        if record.get("status") != TaskStatus.FAILED:
            return {"error": f"任务 {task_id} 当前状态为 {record.get('status')}，无需重试"}

        failed_node = record.get("failed_node", "")
        payload = record.get("retry_payload", {}) or {}
        business = record.get("business", "")
        period = record.get("period", "")

        # 当前仅支持从「HTML 生成」失败节点恢复（重做本地 HTML 生成，不重算）
        if failed_node in ("html_generation",):
            calc_result = payload.get("calc_result") or {}
            summary = payload.get("summary") or ""
            report_prompt = payload.get("report_prompt") or ""
            if not calc_result:
                return {"error": "缺少重试所需的计算结果，请重新发起报告生成"}

            html_result = retry_local_html_report_delivery(
                business=business,
                period=period,
                calc_result=calc_result,
                report_prompt=report_prompt,
                summary=summary,
            )
            if html_result.get("errors"):
                task_store.fail(task_id, "html_generation", html_result["errors"][0], "可再次调用 retry")
                return {"error": html_result["errors"][0]}

            task_store.update(
                task_id,
                TaskStatus.HTML_GENERATED,
                step="html_generation",
                message="本地 HTML 报告生成完成（重试）",
                report_url=html_result.get("report_url", ""),
                report_path=html_result.get("report_path", ""),
            )
            task_store.update(task_id, TaskStatus.COMPLETED, step="completed", message="分析完成（重试恢复）")
            return {
                "success": True,
                "task_id": task_id,
                "status": TaskStatus.COMPLETED,
                "report_url": html_result.get("report_url", ""),
                "retried_node": failed_node,
            }

        return {
            "error": f"失败节点 {failed_node} 不支持从该节点恢复，可重试的节点：html_generation",
            "task_id": task_id,
        }


# 单例实例
skill_based_agent = SkillBasedAgent()


# 兼容旧接口
class AnalysisAgent(SkillBasedAgent):
    """兼容旧接口的Agent"""
    pass


analysis_agent = SkillBasedAgent()
