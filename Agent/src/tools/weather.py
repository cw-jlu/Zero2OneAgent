"""
天气查询工具（真实 API 版本）。
使用免 Key 的 wttr.in 服务获取全球实时天气。
"""
import requests
from tool_registry import ToolSpec, ToolResult


SPEC = ToolSpec(
    name="weather",
    description="查询指定城市的当前实时天气信息，包括温度、天气状况等。",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，英文拼音或英文效果更佳，例如 'Beijing'、'Shanghai'、'Tokyo'"
            }
        },
        "required": ["city"]
    }
)


def handler(args: dict) -> ToolResult:
    city = args.get("city", "").strip()
    if not city:
        return ToolResult(ok=False, output="", error="请提供城市名称")

    try:
        # url 参数中 ?m 代表使用公制单位（摄氏度），format=3 返回精简的一行摘要
        url = f"https://wttr.in/{city}?m&format=3"
        response = requests.get(url, timeout=8)
        
        if response.status_code == 200:
            weather_info = response.text.strip()
            return ToolResult(ok=True, output=f"实时天气信息：\n{weather_info}")
        else:
            return ToolResult(ok=False, output="", error=f"天气接口返回异常 (Code: {response.status_code})")
            
    except Exception as e:
        return ToolResult(ok=False, output="", error=f"请求天气服务失败: {str(e)}")
