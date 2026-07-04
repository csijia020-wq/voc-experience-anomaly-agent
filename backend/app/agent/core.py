"""
Agent核心逻辑 - 基于Skill架构的实现

整合skill文件定义的工具和工作流
"""
from typing import Dict, Any, List, Optional, AsyncGenerator
import json
import asyncio
import re

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm import llm_service
from services.mock_data import mock_data_service
from app.agent.tools.anomaly_calc import anomaly_calc, ANOMALY_CALC_TOOL
from app.agent.tools.query_friday_data import query_friday_data, QUERY_FRIDAY_TOOL
from app.agent.prompts.intent import build_intent_messages
from app.agent.prompts.planning import (
    build_anomaly_calc_thinking,
    build_data_query_thinking,
    build_intent_thinking,
    build_report_generation_thinking,
)
from app.agent.prompts.report import (
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


class SkillBasedAgent:
    """基于Skill架构的体验异动分析Agent"""

    def __init__(self):
        self.llm = llm_service
        self.data_service = mock_data_service
        self.skills = {
            "friday-mcp-query": skill_loader.load_skill("friday-mcp-query"),
            "experience-anomaly-report": skill_loader.load_skill("experience-anomaly-report"),
            "scheduled-message": skill_loader.load_skill("scheduled-message"),
            "s3plus-upload": skill_loader.load_skill("s3plus-upload")
        }

    def recognize_intent(self, user_input: str) -> Dict[str, Any]:
        """
        识别用户意图

        Args:
            user_input: 用户输入

        Returns:
            意图识别结果
        """
        if not user_input or user_input.strip() == "":
            return {
                "intent": "generate_report",
                "business": "到餐客服",
                "period": "上周",
                "confidence": 0.6,
                "error": "输入为空"
            }

        # Demo核心链路优先使用规则解析，避免LLM可用时把明确的周报/异动请求误判为闲聊。
        deterministic_keywords = [
            "报告", "周报", "分析", "生成", "异动", "万服",
            "查询", "查一下", "查下", "提取", "数据", "指标",
            "拉一下", "出一份", "帮我做", "帮我看", "看下", "看看", "复盘",
            "定时", "提醒", "计划", "每周", "每天", "自动发送"
        ]
        if any(keyword in user_input for keyword in deterministic_keywords):
            return self._parse_intent_fallback(user_input)

        # 构建带skill上下文的意图识别prompt
        skill_context = self.skills.get("friday-mcp-query", "")
        messages = build_intent_messages(user_input, skill_context)

        try:
            response = self.llm.chat(messages, temperature=0.3)

            # 清理响应
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.startswith('```'):
                clean_response = clean_response[3:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()

            return self._normalize_intent_result(json.loads(clean_response), user_input)

        except (json.JSONDecodeError, Exception) as e:
            return self._parse_intent_fallback(user_input)

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

    def _normalize_intent_result(self, result: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """统一LLM和规则解析的意图结构，保留旧字段兼容。"""
        if not isinstance(result, dict):
            result = {}

        allowed_intents = {"generate_report", "query_data", "schedule_task", "chat"}
        intent = result.get("intent") or "generate_report"
        if intent not in allowed_intents:
            report_keywords = ["报告", "周报", "月报", "分析", "生成", "提取", "复盘", "异动", "指标"]
            intent = "generate_report" if any(kw in user_input for kw in report_keywords) else "chat"

        business = result.get("business") or "到餐客服"
        period = result.get("period") or "上周"

        explicit_period = self._parse_explicit_week_period(str(period))
        if explicit_period:
            period = explicit_period

        normalized = {
            "intent": intent,
            "business": business,
            "business_source": result.get("business_source") or ("default_demo" if business == "到餐客服" and "到餐" not in user_input else "explicit_user_input"),
            "period": period,
            "period_source": result.get("period_source") or ("default_demo" if period == "上周" and "上周" not in user_input else "explicit_user_input"),
            "comparison_type": result.get("comparison_type") or "yoy",
            "granularity": result.get("granularity") or "weekly",
            "needs_clarification": bool(result.get("needs_clarification", False)),
            "unsupported_reason": result.get("unsupported_reason") or "",
            "confidence": float(result.get("confidence", 0.7) or 0.7),
        }

        if normalized["business"] not in self._supported_businesses():
            normalized["unsupported_reason"] = f"当前项目不支持业务：{normalized['business']}"

        return normalized

    def _parse_intent_fallback(self, user_input: str) -> Dict[str, Any]:
        """备用意图解析"""
        result = {
            "intent": "generate_report",
            "business": "到餐客服",
            "period": "上周",
            "business_source": "default_demo",
            "period_source": "default_demo",
            "comparison_type": "yoy",
            "granularity": "weekly",
            "needs_clarification": False,
            "unsupported_reason": "",
            "confidence": 0.7
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
        elif any(kw in user_input for kw in query_keywords) and not any(kw in user_input for kw in report_keywords):
            result["intent"] = "query_data"
        else:
            result["intent"] = "generate_report"

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

        current_data = query_result.get("current_data", [])
        compare_data = query_result.get("compare_data", [])
        daily_current = query_result.get("daily_current", [])
        daily_compare = query_result.get("daily_compare", [])
        dimension_availability = query_result.get("dimension_availability", {})
        meta = query_result.get("meta", {})

        # 步骤2：异动计算（调用anomaly_calc工具）
        calc_result = execute_tool("anomaly_calc", {
            "current_data": current_data,
            "compare_data": compare_data,
            "daily_current": daily_current,
            "daily_compare": daily_compare,
            "dimension_availability": dimension_availability
        })

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

        # 组装完整报告
        return self._format_report_payload(
            business,
            period,
            calc_result,
            meta,
            summary,
            llm_error,
            locals().get("llm_error_code")
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
        llm_error_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """整理成前端旧字段和新版结构都能消费的报告对象。"""
        overall = calc_result.get("overall", {})
        dim = calc_result.get("dim", {})
        payload = {
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
            "dimensions": self._normalize_dimensions(dim.get("detail", {})),
            "summary": summary,
            "calc_result": calc_result,
            "meta": meta,
            "data_note": "本项目使用模拟数据，仅用于求职作品集演示，不代表真实生产数据。"
        }
        if llm_error:
            payload["llm_error"] = llm_error
        if llm_error_code:
            payload["llm_error_code"] = llm_error_code
        return payload

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
                service_change_ratio = item.get("service_change_ratio", item.get("contrib_wanfu", 0))
                dimensions[dim_type].append({
                    "name": item.get("name", ""),
                    "current_value": item.get("curr_service", 0),
                    "compare_value": item.get("prev_service", 0),
                    "delta": item.get("delta", 0),
                    "yoy": item.get("yoy", 0),
                    "service_change_ratio": service_change_ratio,
                    "contribution": service_change_ratio
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
            f"{x.get('name')}（{x.get('dim_type')}，服务量变化占比{self._format_ratio_percent(x.get('service_change_ratio', x.get('contrib_wanfu', 0)))}）"
            for x in top_up
        ]) or "无明显推高因素"
        down_text = "、".join([
            f"{x.get('name')}（{x.get('dim_type')}，服务量变化占比{self._format_ratio_percent(x.get('service_change_ratio', x.get('contrib_wanfu', 0)))}）"
            for x in top_down
        ]) or "无明显压低因素"
        direction = "上升" if overall.get("yoy", 0) > 0 else "下降" if overall.get("yoy", 0) < 0 else "持平"
        return {
            "summary": (
                f"【模拟数据说明】本报告基于项目内模拟数据生成，仅用于求职作品集演示。<br>"
                f"【核心指标】{business}{period}本期万服为{overall.get('current', 0)}，"
                f"对比期万服为{overall.get('compare', 0)}，同比{direction}{overall.get('yoy', 0)}%，"
                f"差值为{overall.get('delta', 0)}。服务量为{overall.get('service_cnt', 0)}，"
                f"订单量为{overall.get('order_cnt', 0)}。<br>"
                f"【主要推高因素】{up_text}。<br>"
                f"【主要压低因素】{down_text}。<br>"
                f"【口径说明】服务量变化占比 = 某因素服务量变化 / 本期整体服务量，用于衡量因素变化与整体异动的相对关联程度，不能证明因果关系。<br>"
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
        period: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式生成报告

        Args:
            business: 业务名称
            period: 时间周期

        Yields:
            分析步骤和数据
        """
        # 步骤1：意图识别
        yield {
            "type": "step",
            "data": {"step": "intent_recognition", "status": "completed", "message": "意图识别完成"}
        }
        
        yield {
            "type": "thinking",
            "data": {"step": "intent_recognition", "content": build_intent_thinking(business, period)}
        }

        # 步骤2：查询数据
        yield {
            "type": "step",
            "data": {"step": "data_query", "status": "running", "message": "正在查询数据..."}
        }

        yield {
            "type": "thinking",
            "data": {"step": "data_query", "content": build_data_query_thinking(business, period)}
        }

        query_result = execute_tool("query_friday_data", {
            "business": business,
            "period": period,
            "granularity": "weekly"
        })

        if "error" in query_result:
            yield {"type": "error", "data": {"message": query_result["error"]}}
            return

        current_data = query_result.get("current_data", [])
        compare_data = query_result.get("compare_data", [])
        daily_current = query_result.get("daily_current", [])
        daily_compare = query_result.get("daily_compare", [])
        dimension_availability = query_result.get("dimension_availability", {})
        meta = query_result.get("meta", {})

        yield {
            "type": "step",
            "data": {"step": "data_query", "status": "completed", "message": f"数据查询完成，本期{len(current_data)}条记录"}
        }

        # 步骤3：异动计算
        yield {
            "type": "step",
            "data": {"step": "anomaly_calc", "status": "running", "message": "正在计算异动指标..."}
        }

        yield {
            "type": "thinking",
            "data": {"step": "anomaly_calc", "content": build_anomaly_calc_thinking()}
        }

        calc_result = execute_tool("anomaly_calc", {
            "current_data": current_data,
            "compare_data": compare_data,
            "daily_current": daily_current,
            "daily_compare": daily_compare,
            "dimension_availability": dimension_availability
        })

        overall = calc_result.get("overall", {})
        yield {
            "type": "step",
            "data": {"step": "anomaly_calc", "status": "completed", "message": f"计算完成，万服同比{overall.get('yoy', 0)}%"}
        }

        yield {
            "type": "thinking",
            "data": {"step": "anomaly_calc", "content": build_anomaly_calc_thinking(overall, calc_result)}
        }

        # 步骤4：生成报告
        yield {
            "type": "step",
            "data": {"step": "report_generation", "status": "running", "message": "正在生成分析报告..."}
        }

        report_prompt = self._build_report_prompt(business, period, calc_result, meta)

        messages = [
            {"role": "system", "content": "你是一个专业的体验异动分析助手。"},
            {"role": "user", "content": report_prompt}
        ]

        yield {
            "type": "thinking",
            "data": {"step": "report_generation", "content": build_report_generation_thinking()}
        }

        # 流式输出
        summary_chunks = []
        llm_error = None
        try:
            async for chunk in self.llm.chat_stream(messages, temperature=0.5):
                summary_chunks.append(chunk)
                yield {"type": "text", "data": chunk}
            summary = "".join(summary_chunks)
        except Exception as e:
            llm_error = getattr(e, "user_message", str(e))
            llm_error_code = getattr(e, "code", "LLM_API_ERROR")
            summary = self._build_fallback_summary(business, period, calc_result, meta, llm_error)
            yield {"type": "text", "data": summary}

        yield {
            "type": "step",
            "data": {
                "step": "report_generation",
                "status": "completed",
                "message": "报告生成完成" if llm_error is None else "模型不可用，已生成降级报告"
            }
        }

        # 最终报告
        yield {
            "type": "report",
            "data": self._format_report_payload(
                business,
                period,
                calc_result,
                meta,
                summary,
                llm_error,
                locals().get("llm_error_code")
            )
        }

        yield {"type": "done", "data": {"message": "分析完成"}}

    def process_with_tools(self, user_input: str) -> Dict[str, Any]:
        """
        使用工具处理用户请求

        Args:
            user_input: 用户输入

        Returns:
            处理结果
        """
        # 识别意图
        intent_result = self.recognize_intent(user_input)

        business = intent_result.get("business", "到餐客服")
        period = intent_result.get("period", "上周")
        intent = intent_result.get("intent", "generate_report")

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
                "result": {"message": "定时任务功能开发中，请稍后..."}
            }
        else:
            return {
                "intent": intent_result,
                "result": {"message": "我理解了，请告诉我您想做什么？"}
            }


# 单例实例
skill_based_agent = SkillBasedAgent()


# 兼容旧接口
class AnalysisAgent(SkillBasedAgent):
    """兼容旧接口的Agent"""
    pass


analysis_agent = SkillBasedAgent()
