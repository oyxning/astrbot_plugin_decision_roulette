import asyncio
import random
import shlex
from typing import List

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.core.utils.session_waiter import session_waiter, SessionController

# --- 最终美化版: 静态决策结果卡的 HTML + CSS 模板 ---
RESULT_CARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;700&family=Noto+Sans+SC:wght@400;700&display=swap');
    body { 
        font-family: 'Poppins', 'Noto Sans SC', sans-serif; 
        background-color: #f4f7fe;
        margin: 0;
        padding: 24px;
        display: flex;
        justify-content: center;
        align-items: center;
    }
    .card {
        background: #ffffff;
        border-radius: 24px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.08);
        width: 500px;
        padding: 32px;
        border: 1px solid #f0f0f0;
    }
    .header {
        text-align: center;
        margin-bottom: 28px;
    }
    .header h1 {
        font-size: 28px;
        color: #1a202c;
        margin: 0;
        font-weight: 700;
        letter-spacing: 1px;
    }
    .header p {
        font-size: 15px;
        color: #718096;
        margin-top: 6px;
    }
    .options-list {
        margin: 0;
        padding: 0;
        list-style: none;
    }
    .options-list li {
        font-size: 17px;
        padding: 16px 20px;
        margin-bottom: 12px;
        border-radius: 12px;
        color: #4a5568;
        background-color: #f7fafc;
        border: 1px solid #edf2f7;
        font-weight: 500;
        transition: all 0.2s ease-in-out;
    }
    .result {
        color: white !important;
        font-weight: 700;
        background: linear-gradient(90deg, #5e72e4 0%, #825ee4 100%);
        box-shadow: 0 8px 20px rgba(94, 114, 228, 0.4);
        border: none;
        position: relative;
    }
    .result::before {
        content: '👑';
        position: absolute;
        left: 20px;
        top: 50%;
        transform: translateY(-50%);
        font-size: 20px;
        animation: breath 2s ease-in-out infinite;
    }
    .result span {
        display: block;
        margin-left: 35px; /* 为皇冠留出空间 */
    }
    @keyframes breath {
        0%, 100% { transform: translateY(-50%) scale(1); }
        50% { transform: translateY(-50%) scale(1.15); }
    }
</style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h1>最终决定</h1>
            <p>一切皆是命运石之门的选择</p>
        </div>
        <ul class="options-list">
            {% for option in options %}
                {% if option == result %}
                    <li class="result"><span>{{ option }}</span></li>
                {% else %}
                    <li>{{ option }}</li>
                {% endif %}
            {% endfor %}
        </ul>
    </div>
</body>
</html>
"""

@register(
    "decision_roulette",
    "luminestory",
    "一个通过静态卡片帮助用户做决策的趣味实用插件",
    "1.0.0",
    "https://github.com/oyxning/astrbot_plugin_decision_roulette"
)
class DecisionRoulettePlugin(Star):

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config if config else {}
        self.command_blacklist = frozenset(["decide", "决定", "抽奖"])


    @filter.command("decide", alias={"决定", "抽奖"})
    async def decide_starter(self, event: AstrMessageEvent):
        max_options = self.config.get("max_options", 12)
        timeout = self.config.get("session_timeout", 60)

        options_str = event.message_str
        
        try:
            parsed_options = shlex.split(options_str) if options_str else []
            options_list = list(dict.fromkeys(parsed_options))
        except ValueError:
            yield event.plain_result("输入的参数格式有误，请检查您的引号是否匹配。")
            return
        
        if not options_list:
            try:
                @session_waiter(timeout=timeout)
                async def collect_options(controller: SessionController, sub_event: AstrMessageEvent):
                    nonlocal options_list
                    msg = sub_event.message_str.strip()
                    
                    if msg.lower() in ["好了", "ok", "开始"]:
                        controller.stop()
                        return

                    if msg and msg not in options_list:
                        options_list.append(msg)
                        if len(options_list) >= max_options:
                            await sub_event.send(event.plain_result(f"选项已达上限({max_options}个)，即将开始。"))
                            controller.stop()
                        else:
                            await sub_event.send(event.plain_result(f"已添加选项 '{msg}'。继续添加或发送'好了'开始。"))
                    elif msg in options_list:
                        await sub_event.send(event.plain_result(f"选项 '{msg}' 已经存在了哦。"))

                    controller.keep(timeout=timeout, reset_timeout=True)

                yield event.plain_result(f"好的，请在{timeout}秒内发送选项，每个选项一条消息。完成后请发送 '好了' 或 'ok'。")
                await collect_options(event)

            except TimeoutError:
                yield event.plain_result("选项收集超时。")
            except Exception as e:
                logger.error(f"决策会话出错: {e}")
                yield event.plain_result("会话出现未知错误。")

        final_options = [opt for opt in options_list if opt.lower() not in self.command_blacklist]

        if len(final_options) < 2:
            yield event.plain_result("有效选项不足两个（已自动过滤命令本身），无法开始决策。")
            return

        result = random.choice(final_options)
        
        data = { "options": final_options, "result": result }
        
        try:
            image_url = await self.html_render(RESULT_CARD_TEMPLATE, data)
            yield event.image_result(image_url)
        except Exception as e:
            logger.error(f"渲染决策卡片失败: {e}")
            yield event.plain_result(f"渲染卡片时出错，但随机结果是：**{result}**")

    async def terminate(self):
        logger.info("决策轮盘插件已卸载。")