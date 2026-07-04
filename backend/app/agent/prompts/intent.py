"""Intent recognition prompts."""

from typing import Dict, List


INTENT_SYSTEM_PROMPT = (
    "你是 VoC 体验异动分析 Agent 的意图识别器。"
    "你的任务是把用户自然语言解析成结构化 JSON，不生成报告正文。"
    "必须只返回纯 JSON。"
)


def build_intent_prompt(user_input: str, skill_context: str = "") -> str:
    """Build the user prompt for LLM-based intent recognition."""
    skill_note = ""
    if skill_context:
        skill_note = "\n\n## 可参考的业务技能上下文\n" + skill_context[:1200]

    return f"""请把用户输入解析成 VoC 体验异动分析 Agent 可执行的 JSON。

## 用户输入
{user_input}

## 支持的 intent
- generate_report：生成周报、月报、异动分析报告、复盘报告。
- query_data：只查询数据或指标，不要求生成完整报告。
- schedule_task：定时、提醒、计划任务。
- chat：普通闲聊，或无法映射到当前 Agent 能力的请求。

## 自然语言表达映射
- “生成、提取、拉一下、出一份、帮我做、帮我看、看下、看看、复盘、分析” + 周报/报告/异动/指标，通常识别为 generate_report。
- “查一下、查下、查询、看数据、指标是多少” 且没有要求报告，识别为 query_data。
- “每周一、每天、定时、提醒、自动发送、计划” 识别为 schedule_task。

## 支持业务和别名
- 到餐客服：到餐、餐饮、餐客服。
- 闪购客服：闪购、即时零售。
- 企客业务：企客、企业客户。
- 如果用户没有明确业务，Demo 默认 business 为“到餐客服”，business_source 为“default_demo”。
- 如果用户明确提到不支持的业务，保留用户业务名，并填写 unsupported_reason。

## 周期识别规则
- 上周 -> 上周。
- 本周、最近七天、最近一周 -> 本周。
- 上月 -> 上月；本月 -> 本月。
- 2026年W2、2026W2、2026-W02、2026年第2周 -> 2026W02。
- 2026年3月、2026-03 -> 2026-03。
- 如果用户明确给了周期，不要覆盖成上周。
- 如果没有周期，默认 period 为“上周”，period_source 为“default_demo”。

## 输出 JSON 字段
{{
  "intent": "generate_report | query_data | schedule_task | chat",
  "business": "到餐客服 | 闪购客服 | 企客业务 | 用户提到的其他业务",
  "business_source": "explicit_user_input | default_demo",
  "period": "上周 | 本周 | 上月 | 本月 | 2026W02 | 2026-03",
  "period_source": "explicit_user_input | default_demo",
  "comparison_type": "yoy",
  "granularity": "weekly",
  "needs_clarification": false,
  "unsupported_reason": "",
  "confidence": 0.0
}}

## 示例
用户：帮我提取2026年W2的周报
输出：{{"intent":"generate_report","business":"到餐客服","business_source":"default_demo","period":"2026W02","period_source":"explicit_user_input","comparison_type":"yoy","granularity":"weekly","needs_clarification":false,"unsupported_reason":"","confidence":0.9}}

用户：拉一下闪购最近七天体验异动
输出：{{"intent":"generate_report","business":"闪购客服","business_source":"explicit_user_input","period":"本周","period_source":"explicit_user_input","comparison_type":"yoy","granularity":"weekly","needs_clarification":false,"unsupported_reason":"","confidence":0.9}}

用户：查一下企客2026年3月数据
输出：{{"intent":"query_data","business":"企客业务","business_source":"explicit_user_input","period":"2026-03","period_source":"explicit_user_input","comparison_type":"yoy","granularity":"weekly","needs_clarification":false,"unsupported_reason":"","confidence":0.86}}

只返回 JSON，不要 Markdown，不要解释。{skill_note}"""


def build_intent_messages(user_input: str, skill_context: str = "") -> List[Dict[str, str]]:
    """Build chat messages for intent recognition."""
    return [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": build_intent_prompt(user_input, skill_context)},
    ]
