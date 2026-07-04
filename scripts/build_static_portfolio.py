"""Build the GitHub Pages static portfolio from the real frontend report page."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "project_delivery" / "vibe_coding_prototype.html"
STATIC_PAGE = ROOT / "docs" / "index.html"


def build_static_report_data() -> dict:
    """Use the same deterministic backend calculation path without calling an LLM."""
    os.environ["DEMO_DETERMINISTIC"] = "true"
    os.environ["DEMO_SEED"] = "20260702"
    sys.path.insert(0, str(BACKEND))

    from app.agent.core import analysis_agent
    from app.agent.tools.anomaly_calc import anomaly_calc
    from app.agent.tools.query_friday_data import query_friday_data

    business = "到餐客服"
    period = "上周"
    query = query_friday_data(business=business, period=period, granularity="weekly")
    calc = anomaly_calc(
        current_data=query["current_data"],
        compare_data=query["compare_data"],
        daily_current=query["daily_current"],
        daily_compare=query["daily_compare"],
        dimension_availability=query["dimension_availability"],
    )
    meta = query.get("meta", {})
    llm_error = "实时模型暂时不可用，系统已使用结构化计算结果生成降级报告。"
    summary = analysis_agent._build_fallback_summary(business, period, calc, meta, llm_error)
    return analysis_agent._format_report_payload(
        business,
        period,
        calc,
        meta,
        summary,
        llm_error,
        "LLM_CONNECTION_ERROR",
    )


def extract_real_frontend_shell(source: str) -> tuple[str, str]:
    """Return the page HTML before the API script and the report rendering helpers."""
    pre_script = source.split("    <script>", 1)[0]
    pre_script = pre_script.replace(
        "<title>VoC 体验异动分析 Agent</title>",
        "<title>VoC 体验异动分析 Agent | 静态作品集演示版</title>",
    )
    pre_script = pre_script.replace(
        "模拟作品集 Demo</span>",
        "静态作品集演示版 · 不调用真实 DeepSeek</span>",
    )

    script = source.split("    <script>", 1)[1].split("    </script>", 1)[0]
    helpers_start = script.index("        function formatServiceChangeRatio")
    helpers_end = script.index("        // 页面加载完成后初始化")
    helpers = script[helpers_start:helpers_end]
    return pre_script, helpers


def build_static_script(report: dict, helpers: str) -> str:
    report_json = json.dumps(report, ensure_ascii=False, indent=10)
    static_behavior = f"""        const STATIC_REPORT_DATA = {report_json};

        const STATIC_THINKING_STEPS = [
            ['intent_recognition', '识别为生成周报；业务为到餐客服；时间为上周；对比方式为去年同期。'],
            ['data_query', '读取作品集内置的固定模拟 VoC 数据，生成周粒度指标、日趋势和维度明细。'],
            ['anomaly_calc', '计算本期万服、去年同期万服、同比变化、服务量变化占比，并按维度排序主要因素。'],
            ['report_generation', '静态作品集版不调用真实 DeepSeek，直接展示与后端降级报告一致的结构化报告。']
        ];

        let currentReportData = STATIC_REPORT_DATA;

        function switchTab(tab) {{
            document.querySelectorAll('.tab-btn').forEach(btn => {{
                btn.classList.remove('tab-active');
                btn.classList.add('text-gray-500');
            }});
            const activeButton = document.querySelector(`[data-tab="${{tab}}"]`);
            if (activeButton) {{
                activeButton.classList.add('tab-active');
                activeButton.classList.remove('text-gray-500');
            }}

            if (tab === 'chat') {{
                document.getElementById('chatPanel').classList.remove('hidden');
                document.getElementById('reportPanel').classList.add('hidden');
            }} else {{
                document.getElementById('chatPanel').classList.add('hidden');
                document.getElementById('reportPanel').classList.remove('hidden');
                renderReport(currentReportData);
                initCharts();
                resizeDailyChartSoon();
            }}
        }}

        function switchDimTab(dim) {{
            document.querySelectorAll('.dim-tab').forEach(btn => {{
                btn.classList.remove('text-red-600', 'border-b-2', 'border-red-600');
                btn.classList.add('text-gray-500');
            }});
            const activeButton = document.querySelector(`[data-dim="${{dim}}"]`);
            if (activeButton) {{
                activeButton.classList.add('text-red-600', 'border-b-2', 'border-red-600');
                activeButton.classList.remove('text-gray-500');
            }}

            document.querySelectorAll('.dim-content').forEach(content => {{
                content.classList.add('hidden');
            }});
            const activeContent = document.getElementById(`dim_${{dim}}`);
            if (activeContent) {{
                activeContent.classList.remove('hidden');
            }}
        }}

        function sendMessage() {{
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            if (!message) return;

            const messageList = document.getElementById('messageList');
            messageList.innerHTML = '';
            addMessage(message, 'user');
            input.value = '';
            document.getElementById('welcomeArea').classList.add('hidden');
            document.getElementById('loadingArea').classList.remove('hidden');
            document.getElementById('loadingText').textContent = '正在执行静态演示链路...';

            STATIC_THINKING_STEPS.forEach((item, index) => {{
                window.setTimeout(() => {{
                    handleThinking({{ step: item[0], content: item[1] }});
                    document.getElementById('loadingText').textContent = `${{item[1]}} ✓`;
                    if (index === STATIC_THINKING_STEPS.length - 1) {{
                        window.setTimeout(() => {{
                            handleText(STATIC_REPORT_DATA.summary);
                            handleReport(STATIC_REPORT_DATA);
                        }}, 360);
                    }}
                }}, 420 * (index + 1));
            }});
        }}

        function handleThinking(thinkingData) {{
            const messageList = document.getElementById('messageList');
            messageList.classList.remove('hidden');
            document.getElementById('welcomeArea').classList.add('hidden');

            const thinkingDiv = document.createElement('div');
            thinkingDiv.className = 'flex justify-start animate-slide-up mb-2';
            const stepNames = {{
                intent_recognition: '意图识别',
                data_query: '数据查询',
                anomaly_calc: '异动计算',
                report_generation: '报告生成'
            }};
            const stepName = stepNames[thinkingData.step] || thinkingData.step;

            thinkingDiv.innerHTML = `
                <div class="max-w-md w-full">
                    <div class="flex items-center space-x-2 mb-1">
                        <svg class="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path>
                        </svg>
                        <span class="text-xs font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded">${{stepName}}</span>
                    </div>
                    <div class="thinking-bubble px-4 py-3 rounded-lg rounded-bl-none text-sm text-gray-700">
                        ${{escapeHtml(thinkingData.content)}}
                    </div>
                </div>
            `;

            messageList.appendChild(thinkingDiv);
            messageList.scrollTop = messageList.scrollHeight;
        }}

        function handleText(text) {{
            const messageList = document.getElementById('messageList');
            messageList.classList.remove('hidden');
            document.getElementById('welcomeArea').classList.add('hidden');

            let textMessage = document.getElementById('streamingText');
            if (!textMessage) {{
                textMessage = document.createElement('div');
                textMessage.id = 'streamingText';
                textMessage.className = 'flex justify-start animate-slide-up';
                textMessage.dataset.rawMarkdown = '';
                textMessage.innerHTML = `
                    <div class="chat-report-bubble px-5 py-4 bg-gray-100 text-gray-800 rounded-lg rounded-bl-none">
                        <div id="streamingContent" class="report-markdown"></div>
                    </div>
                `;
                messageList.appendChild(textMessage);
            }}

            const content = textMessage.querySelector('#streamingContent');
            textMessage.dataset.rawMarkdown = (textMessage.dataset.rawMarkdown || '') + text;
            content.innerHTML = renderReportMarkdown(textMessage.dataset.rawMarkdown);
            messageList.scrollTop = messageList.scrollHeight;
        }}

        function handleReport(reportData) {{
            currentReportData = reportData;
            document.getElementById('loadingArea').classList.add('hidden');
            const streamingText = document.getElementById('streamingText');
            if (streamingText) {{
                streamingText.id = '';
            }}
            addMessage('报告已生成，正在切换到完整报告展示页。', 'ai');
            window.setTimeout(() => switchTab('report'), 500);
        }}

        function addMessage(text, type) {{
            const messageList = document.getElementById('messageList');
            messageList.classList.remove('hidden');
            document.getElementById('welcomeArea').classList.add('hidden');

            const messageDiv = document.createElement('div');
            messageDiv.className = `flex ${{type === 'user' ? 'justify-end' : 'justify-start'}} animate-slide-up`;
            if (type === 'user') {{
                messageDiv.innerHTML = `<div class="max-w-xs px-4 py-2 bg-red-600 text-white rounded-lg rounded-br-none">${{escapeHtml(text)}}</div>`;
            }} else {{
                messageDiv.innerHTML = `<div class="max-w-md px-4 py-2 bg-gray-100 text-gray-800 rounded-lg rounded-bl-none">${{escapeHtml(text)}}</div>`;
            }}
            messageList.appendChild(messageDiv);
            messageList.scrollTop = messageList.scrollHeight;
        }}

        function quickAction(business, period) {{
            switchTab('chat');
            const input = document.getElementById('chatInput');
            input.value = `生成${{business}}${{period}}周报`;
            sendMessage();
        }}

        function handleKeyPress(event) {{
            if (event.key === 'Enter') {{
                sendMessage();
            }}
        }}

        function showTaskModal() {{
            document.getElementById('taskModal').classList.remove('hidden');
        }}

        function closeTaskModal() {{
            document.getElementById('taskModal').classList.add('hidden');
        }}

        function showLogModal() {{
            document.getElementById('logModal').classList.remove('hidden');
        }}

        function closeLogModal() {{
            document.getElementById('logModal').classList.add('hidden');
        }}

        function createTask() {{
            const business = document.getElementById('taskBusiness').value;
            showToast(`静态演示：${{business}}周报任务已展示，真实创建请运行后端版本。`);
            closeTaskModal();
        }}

        function showToast(message) {{
            const toast = document.getElementById('toast');
            document.getElementById('toastMessage').textContent = message;
            toast.classList.remove('hidden');
            setTimeout(() => {{
                toast.classList.add('hidden');
            }}, 3000);
        }}

"""
    initializer = """
        document.addEventListener('DOMContentLoaded', () => {
            renderReport(STATIC_REPORT_DATA);
            switchTab('report');
        });
"""
    return static_behavior + helpers + initializer


def main() -> None:
    report = build_static_report_data()
    source = FRONTEND.read_text(encoding="utf-8")
    pre_script, helpers = extract_real_frontend_shell(source)
    static_script = build_static_script(report, helpers)
    html = pre_script + "    <script>\n" + static_script + "    </script>\n</body>\n</html>\n"
    STATIC_PAGE.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
