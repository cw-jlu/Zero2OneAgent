"""
天气查询工具（mock 版本）。
模拟几个城市的天气数据，实际可以接 OpenWeather 之类的 API。
"""
from tool_registry import ToolSpec, ToolResult


SPEC = ToolSpec(
    name="weather",
    description="查询指定城市的当前天气信息，包括温度、湿度、天气状况。",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，例如 '北京'、'上海'、'Tokyo'"
            }
        },
        "required": ["city"]
    }
)

# mock 数据
_WEATHER_DATA = {
    "北京": {"temp": 32, "humidity": 45, "condition": "晴", "wind": "北风3级"},
    "上海": {"temp": 28, "humidity": 78, "condition": "多云", "wind": "东南风2级"},
    "广州": {"temp": 35, "humidity": 82, "condition": "雷阵雨", "wind": "南风4级"},
    "深圳": {"temp": 33, "humidity": 80, "condition": "阵雨转多云", "wind": "西南风3级"},
    "杭州": {"temp": 30, "humidity": 70, "condition": "阴", "wind": "东风2级"},
    "tokyo": {"temp": 26, "humidity": 65, "condition": "Partly Cloudy", "wind": "SE 10km/h"},
    "new york": {"temp": 22, "humidity": 55, "condition": "Sunny", "wind": "W 15km/h"},
}


def handler(args: dict) -> ToolResult:
    city = args.get("city", "").strip()
    if not city:
        return ToolResult(ok=False, output="", error="请提供城市名称")

    # 不区分大小写匹配
    data = _WEATHER_DATA.get(city) or _WEATHER_DATA.get(city.lower())

    if data:
        output = (
            f"🌤 {city} 当前天气：\n"
            f"  温度: {data['temp']}°C\n"
            f"  湿度: {data['humidity']}%\n"
            f"  天气: {data['condition']}\n"
            f"  风力: {data['wind']}"
        )
        return ToolResult(ok=True, output=output)
    else:
        # 查不到也别报错，给个合理的兜底
        return ToolResult(
            ok=True,
            output=f"暂时无法获取 {city} 的天气数据。可能是城市名称有误或该城市暂不支持查询。"
        )
