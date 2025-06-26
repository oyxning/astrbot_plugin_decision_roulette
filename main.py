import asyncio
import random
import shlex
from typing import List

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.core.utils.session_waiter import session_waiter, SessionController

# --- 最终优化版: 静态决策结果卡的 HTML + CSS 模板 ---
RESULT_CARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&family=Noto+Sans+SC:wght@400;700&display=swap');
    body { 
        font-family: 'Poppins', 'Noto Sans SC', sans-serif; 
        background: #e0e5ec;
        margin: 0;
        padding: 20px;
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 350px;
    }
    .card {
        background: #e0e5ec;
        border-radius: 20px;
        box-shadow: 9px 9px 16px #a3b1c6, -9px -9px 16px #ffffff;
        width: 480px;
        padding: 30px;
    }
    .header {
        text-align: center;
        margin-bottom: 25px;
    }
    .header h1 {
        font-size: 26px;
        color: #4b5a7a;
        margin: 0;
        font-weight: 600;
    }
    .header p {
        font-size: 14px;
        color: #8c96a5;
        margin-top: 5px;
    }
    .options-list {
        margin: 0;
        padding: 0;
        list-style: none;
    }
    .options-list li {
        font-size: 16px;
        padding: 12px 20px;
        margin-bottom: 12px;
        border-radius: 10px;
        color: #4b5a7a;
        background: #e0e5ec;
        box-shadow: inset 5px 5px 10px #a3b1c6, inset -5px -5px 10px #ffffff;
        transition: all 0.2s ease-in-out;
    }
    .result {
        color: #ffffff !important;
        font-weight: 700;
        background: linear-gradient(145deg, #5b24ff, #8f6afe);
        box-shadow: 5px 5px 10px #a3b1c6, -5px -5px 10px #ffffff;
        transform: scale(1.03);
        position: relative;
    }
    .result::after {
        content: '🎯';
        position: absolute;
        right: 20px;
        top: 50%;
        transform: translateY(-50%) scale(1.2);
        animation: tada 1s ease-in-out;
    }
    @keyframes tada {
        0% {transform: translateY(-50%) scale(1.2);}
        10%, 20% {transform: translateY(-50%) scale(1.1) rotate(-3deg);}
        30%, 50%, 70%, 90% {transform: translateY(-50%) scale(1.3) rotate(3deg);}
        40%, 60%, 80% {transform: translateY(-50%) scale(1.3) rotate(-3deg);}
        100% {transform: translateY(-50%) scale(1.2) rotate(0);}
    }
</style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h1>天选之子</h1>
            <p>命运的轮盘已为你停下</p>
        </div>
        <ul class="options-list">
            {% for option in options %}
                {% if option == result %}
                    <li class="result">{{ option }}</li>
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

        if len(options_list) < 2:
            yield event.plain_result("至少需要两个选项才能开始决策。")
            return

        result = random.choice(options_list)
        
        data = { "options": options_list, "result": result }
        
        try:
            image_url = await self.html_render(RESULT_CARD_TEMPLATE, data)
            yield event.image_result(image_url)
        except Exception as e:
            logger.error(f"渲染决策卡片失败: {e}")
            yield event.plain_result(f"渲染卡片时出错，但随机结果是：**{result}**")

    async def terminate(self):
        logger.info("决策轮盘插件已卸载。")