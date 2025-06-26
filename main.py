import asyncio
import random
from typing import List

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.core.utils.session_waiter import session_waiter, SessionController

# --- 最终修正版: 静态决策结果卡的 HTML + CSS 模板 ---
RESULT_CARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700&display=swap');
    body { 
        font-family: 'Noto Sans SC', sans-serif; 
        background-color: #f7f9fc;
        margin: 0;
        padding: 20px;
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 300px;
    }
    .card {
        background: white;
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        width: 450px;
        padding: 25px;
        border: 1px solid #eef;
    }
    .header {
        text-align: center;
        border-bottom: 2px solid #f0f0f0;
        padding-bottom: 15px;
        margin-bottom: 20px;
    }
    .header h1 {
        font-size: 24px;
        color: #333;
        margin: 0;
    }
    .options-list {
        margin: 0;
        padding: 0;
        list-style: none;
    }
    .options-list li {
        font-size: 16px;
        padding: 10px 15px;
        margin-bottom: 8px;
        border-radius: 8px;
        background-color: #f7f9fc;
        color: #555;
    }
    .result {
        background: linear-gradient(45deg, #6a82fb, #fc5c7d);
        color: white !important;
        font-weight: 700;
        transform: scale(1.05);
        box-shadow: 0 4px 15px rgba(252, 92, 125, 0.4);
    }
</style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h1>命运的抉择！</h1>
        </div>
        <ul class="options-list">
            {% for option in options %}
                {% if option == result %}
                    <li class="result">✨ {{ option }} ✨</li>
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

    @filter.command("decide", alias={"决定", "抽奖"})
    async def decide_starter(self, event: AstrMessageEvent, options_str: str = ""):
        max_options = self.config.get("max_options", 12)
        timeout = self.config.get("session_timeout", 60)

        options_str_cleaned = options_str.strip().strip('"').strip("'")
        options_list = [opt for opt in options_str_cleaned.split() if opt] if options_str_cleaned else []
        
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
                    controller.keep(timeout=timeout, reset_timeout=True)

                yield event.plain_result(f"好的，请在{timeout}秒内发送选项，每个选项一条消息。完成后请发送 '好了' 或 'ok'。")
                await collect_options(event)

            except TimeoutError:
                yield event.plain_result("选项收集超时。")
            except Exception as e:
                logger.error(f"决策会话出错: {e}")
                yield event.plain_result("会话出现未知错误。")

        if len(options_list) < 2:
            yield event.plain_result("至少需要两个选项才能开始决策。")
            return

        result = random.choice(options_list)
        
        data = {
            "options": options_list,
            "result": result
        }
        
        try:
            # --- 最终修正点: 调用 html_render 时只使用文档支持的参数 ---
            image_url = await self.html_render(RESULT_CARD_TEMPLATE, data)
            yield event.image_result(image_url)
        except Exception as e:
            logger.error(f"渲染决策卡片失败: {e}")
            yield event.plain_result(f"渲染卡片时出错，但随机结果是：**{result}**")

    async def terminate(self):
        logger.info("决策轮盘插件已卸载。")