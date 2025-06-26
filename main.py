import asyncio
import random
from typing import List

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.core.utils.session_waiter import session_waiter, SessionController

# --- 动态决策轮盘的 HTML + CSS + JS 模板 (内容不变) ---
ROULETTE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f0f2f5; margin: 0; }
    .wheel-container { text-align: center; }
    .wheel { position: relative; width: 400px; height: 400px; border-radius: 50%; border: 10px solid #fff; box-shadow: 0 0 20px rgba(0,0,0,0.2); overflow: hidden; transition: transform 4s cubic-bezier(0.25, 1, 0.5, 1); }
    .segment { position: absolute; width: 50%; height: 50%; left: 50%; top: 50%; transform-origin: 0% 100%; display: flex; justify-content: center; align-items: center; }
    .segment span { display: block; transform: rotate(45deg); font-weight: bold; color: #333; padding-right: 40px; }
    .pointer { position: absolute; left: 50%; top: -10px; transform: translateX(-50%); width: 0; height: 0; border-left: 20px solid transparent; border-right: 20px solid transparent; border-top: 30px solid #e74c3c; z-index: 10; }
    h1 { color: #333; margin-top: 20px; }
</style>
</head>
<body>
    <div class="wheel-container">
        <div class="pointer"></div>
        <div class="wheel" id="wheel">
            {% for i in range(options|length) %}
            <div class="segment" style="transform: rotate({{ i * (360 / (options|length)) }}deg); background-color: {{ colors[i % colors|length] }};">
                <span>{{ options[i] }}</span>
            </div>
            {% endfor %}
        </div>
        <h1 id="result"></h1>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const wheel = document.getElementById('wheel');
            const finalRotation = {{ final_rotation }};
            setTimeout(() => {
                wheel.style.transform = `rotate(${finalRotation}deg)`;
            }, 100);
            setTimeout(() => {
                document.getElementById('result').innerText = '最终决定是：{{ result }}';
            }, 4500);
        });
    </script>
</body>
</html>
"""

@register(
    "decision_roulette",
    "luminestory",
    "一个通过动态轮盘帮助用户做决策的趣味实用插件",
    "1.0.0",
    "https://github.com/oyxning/astrbot_plugin_decision_roulette"
)
class DecisionRoulettePlugin(Star):

    def __init__(self, context: Context, config: AstrBotConfig = None):
        """
        最终修正版 __init__。
        将 config 参数标记为可选，并正确处理其可能为 None 的情况。
        """
        super().__init__(context)
        self.config = config if config else {} # 关键修正：如果 config 为 None，则初始化为空字典

    @filter.command("decide", alias={"决定", "抽奖"})
    async def decide_starter(self, event: AstrMessageEvent, options_str: str = ""):
        """
        发起一个决策。可以直接提供选项，也可以进入交互模式。
        """
        # --- 最终修正点: 使用 .get() 方法安全地从配置中获取值 ---
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
        result_index = options_list.index(result)
        num_options = len(options_list)
        segment_angle = 360 / num_options
        
        final_rotation = (5 * 360) + (360 - (result_index * segment_angle)) - (segment_angle / 2)
        
        colors = ["#ffcdd2", "#c8e6c9", "#bbdefb", "#fff9c4", "#d1c4e9", "#b2dfdb"]
        
        data = {
            "options": options_list,
            "result": result,
            "final_rotation": final_rotation,
            "colors": colors
        }
        
        try:
            image_url = await self.html_render(ROULETTE_TEMPLATE, data, render_type="gif", render_params={"wait_time": 5000})
            yield event.image_result(image_url)
        except Exception as e:
            logger.error(f"渲染决策轮盘失败: {e}")
            yield event.plain_result(f"渲染轮盘时出错，但随机结果是：**{result}**")

    async def terminate(self):
        logger.info("决策轮盘插件已卸载。")