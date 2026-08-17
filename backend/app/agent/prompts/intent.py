"""Intent recognition prompts."""

from typing import Any, Dict, List, Optional


INTENT_SYSTEM_PROMPT = (
    "你是 VoC 体验异动分析 Agent 的意图识别器。"
    "你的任务是把用户自然语言解析成结构化 JSON，不生成报告正文。"
    "必须只返回纯 JSON。"
)


def _serialize_history(history: Optional[List[Any]]) -> str:
    """把历史消息序列化为「角色：内容」文本，供 LLM 参考补全槽位。"""
    if not history:
        return ""
    lines = []
    for item in history:
        if isinstance(item, dict):
            role = item.get("role", "user")
            content = item.get("content", "")
        else:
            role = getattr(item, "role", "user")
            content = getattr(item, "content", "")
        content = str(content or "").strip()
        if content:
            label = "用户" if role == "user" else "助手"
            lines.append(f"{label}：{content}")
    return "\n".join(lines)


def build_intent_prompt(
    user_input: str,
    skill_context: str = "",
    history: Optional[List[Any]] = None,
) -> str:
    """Build the user prompt for LLM-based intent recognition."""
    skill_note = ""
    if skill_context:
        skill_note = "\n\n## 可参考的业务技能上下文\n" + skill_context[:1200]

    history_note = ""
    history_text = _serialize_history(history)
    if history_text:
        history_note = (
            "\n\n## 对话历史（用于继承缺失槽位）\n"
            f"{history_text}\n\n"
            "如果用户当前输入没有明确业务或周期，但历史对话中已经明确过，"
            "请从历史中继承并填入对应槽位，不要重复追问。"
        )

    return f"""请把用户输入解析成 VoC 体验异动分析 Agent 可执行的 JSON。

## 用户输入
{user_input}
{history_note}
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
- 如果用户没有明确业务，**禁止**默认填“到餐客服”：必须置 needs_clarification=true，并在 llm_response 中追问“请补充业务范围”。
- 如果用户明确提到不支持的业务，保留用户业务名，并填写 unsupported_reason。

## 周期识别规则
- 上周 -> 上周。
- 本周、最近七天、最近一周 -> 本周。
- 上月 -> 上月；本月 -> 本月。
- 2026年W2、2026W2、2026-W02、2026年第2周 -> 2026W02。
- 2026年3月、2026-03 -> 2026-03。
- 如果用户明确给了周期，不要覆盖。
- 如果用户没有明确周期（例如只说“最近”“近期”等模糊词），**禁止**默认填“上周”：必须置 needs_clarification=true，并在 llm_response 中追问“请确认对比周期”。

## 定时任务参数提取（仅 intent=schedule_task 时）
- 从输入提取：business（业务）、schedule_cron（如“每周一上午9点”→ "0 9 * * 1"）、schedule_name（任务名，缺省用「{{business}}周报」）、receiver（接收方，缺省"本地 Demo"）。
- schedule_task 本身**不直接创建**任务，needs_clarification 保持 false（由后端返回确认信息）。

## 输出 JSON 字段
{{
  "intent": "generate_report | query_data | schedule_task | chat",
  "business": "到餐客服 | 闪购客服 | 企客业务 | 用户提到的其他业务 | 缺省为空字符串",
  "business_source": "explicit_user_input | missing",
  "period": "上周 | 本周 | 上月 | 本月 | 2026W02 | 2026-03 | 缺省为空字符串",
  "period_source": "explicit_user_input | missing",
  "comparison_type": "yoy",
  "granularity": "weekly",
  "schedule_cron": "schedule_task 时填写，否则空字符串",
  "schedule_name": "schedule_task 时填写，否则空字符串",
  "receiver": "schedule_task 时填写，否则空字符串",
  "needs_clarification": false,
  "llm_response": "",
  "unsupported_reason": "",
  "confidence": 0.0
}}

- 当缺少 business 或 period 时，needs_clarification 必须为 true，llm_response 为自然语言追问。
- llm_response 仅在 needs_clarification=true 时非空，其余情况保持空字符串。

## 示例
用户：帮我提取到餐客服2026年W2的周报
输出：{{"intent":"generate_report","business":"到餐客服","business_source":"explicit_user_input","period":"2026W02","period_source":"explicit_user_input","comparison_type":"yoy","granularity":"weekly","schedule_cron":"","schedule_name":"","receiver":"","needs_clarification":false,"llm_response":"","unsupported_reason":"","confidence":0.9}}

用户：帮我提取2026年W2的周报（未说明业务）
输出：{{"intent":"generate_report","business":"","business_source":"missing","period":"2026W02","period_source":"explicit_user_input","comparison_type":"yoy","granularity":"weekly","schedule_cron":"","schedule_name":"","receiver":"","needs_clarification":true,"llm_response":"请补充业务范围，例如：到餐客服 2026W02。","unsupported_reason":"","confidence":0.6}}

用户：拉一下闪购最近七天体验异动
输出：{{"intent":"generate_report","business":"闪购客服","business_source":"explicit_user_input","period":"本周","period_source":"explicit_user_input","comparison_type":"yoy","granularity":"weekly","schedule_cron":"","schedule_name":"","receiver":"","needs_clarification":false,"llm_response":"","unsupported_reason":"","confidence":0.9}}

用户：每周一上午9点自动生成到餐客服周报
输出：{{"intent":"schedule_task","business":"到餐客服","business_source":"explicit_user_input","period":"","period_source":"missing","comparison_type":"yoy","granularity":"weekly","schedule_cron":"0 9 * * 1","schedule_name":"到餐客服周报","receiver":"本地 Demo","needs_clarification":false,"llm_response":"","unsupported_reason":"","confidence":0.9}}

只返回 JSON，不要 Markdown，不要解释。{skill_note}"""


def build_intent_messages(
    user_input: str,
    skill_context: str = "",
    history: Optional[List[Any]] = None,
) -> List[Dict[str, str]]:
    """Build chat messages for intent recognition."""
    return [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": build_intent_prompt(user_input, skill_context, history)},
    ]
