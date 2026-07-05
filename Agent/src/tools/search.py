"""
联网搜索工具（免 Key 真实联网版本）。
结合 DuckDuckGo 网页检索与 Wikipedia 百科检索。
当网络环境或代理配置允许时，使用 DuckDuckGo 获取最新网页结果；
否则自动降级为 Wikipedia，保障基础搜索可用性。
"""
import re
import requests
from bs4 import BeautifulSoup
from tool_registry import ToolSpec, ToolResult

SPEC = ToolSpec(
    name="search",
    description="搜索互联网信息。输入查询关键词，返回网页摘要和内容。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            }
        },
        "required": ["query"]
    }
)


def _search_duckduckgo(query: str) -> list[dict]:
    """通过 DuckDuckGo HTML 版抓取搜索结果"""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    
    # requests 会自动应用 .env 中加载的 HTTP_PROXY/HTTPS_PROXY 环境变量
    response = requests.get(url, params=params, headers=headers, timeout=8)
    if response.status_code != 200:
        raise Exception(f"DuckDuckGo 返回错误代码: {response.status_code}")

    soup = BeautifulSoup(response.text, "html.parser")
    elements = soup.find_all("a", class_="result__url")
    
    results = []
    for r in elements[:5]: # 保留前 5 条结果
        title = r.get_text(strip=True)
        link = r.get("href")
        
        # 寻找对应的摘要段落
        snippet_elem = r.find_next("a", class_="result__snippet")
        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
        
        if title and link:
            # 清理 url （DuckDuckGo 的链接会带有跳转前缀）
            if link.startswith("//duckduckgo.com/l/?uddg="):
                # 简单解码
                match = re.search(r"uddg=([^&]+)", link)
                if match:
                    from urllib.parse import unquote
                    link = unquote(match.group(1))
            
            results.append({
                "title": title,
                "link": link,
                "snippet": snippet
            })
    return results


def _search_wikipedia(query: str) -> list[dict]:
    """通过 Wikipedia 开放 API 搜索"""
    url = "https://zh.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "utf8": 1
    }
    headers = {"User-Agent": "Zero2OneAgent/1.0"}
    
    response = requests.get(url, params=params, headers=headers, timeout=8)
    if response.status_code != 200:
        raise Exception(f"Wikipedia API 返回错误代码: {response.status_code}")
        
    data = response.json()
    search_results = data.get("query", {}).get("search", [])
    
    results = []
    for item in search_results[:5]:
        title = item["title"]
        # 去除 Wikipedia 返回文本中的 HTML 标签（如 <span class="searchmatch">）
        snippet = re.sub(r"<[^<]+?>", "", item["snippet"])
        link = f"https://zh.wikipedia.org/wiki/{title}"
        
        results.append({
            "title": title,
            "link": link,
            "snippet": snippet
        })
    return results


def handler(args: dict) -> ToolResult:
    query = args.get("query", "").strip()
    if not query:
        return ToolResult(ok=False, output="", error="搜索关键词不能为空")

    errors = []
    
    # 优先尝试 DuckDuckGo 获取最新全网信息
    try:
        results = _search_duckduckgo(query)
        if results:
            output_lines = [f"🌐 联网搜索结果 (DuckDuckGo) -> 「{query}」:\n"]
            for i, r in enumerate(results, 1):
                output_lines.append(f"{i}. {r['title']}")
                output_lines.append(f"   链接: {r['link']}")
                output_lines.append(f"   摘要: {r['snippet']}\n")
            return ToolResult(ok=True, output="\n".join(output_lines))
    except Exception as e:
        errors.append(f"DuckDuckGo 失败: {str(e)}")

    # 降级尝试 Wikipedia 百科检索
    try:
        results = _search_wikipedia(query)
        if results:
            output_lines = [f"📚 百科搜索结果 (Wikipedia) -> 「{query}」:\n"]
            for i, r in enumerate(results, 1):
                output_lines.append(f"{i}. {r['title']}")
                output_lines.append(f"   链接: {r['link']}")
                output_lines.append(f"   摘要: {r['snippet']}\n")
            return ToolResult(ok=True, output="\n".join(output_lines))
    except Exception as e:
        errors.append(f"Wikipedia 失败: {str(e)}")

    # 双通道均失败时返回报错
    return ToolResult(
        ok=False, 
        output="", 
        error=f"无法获取搜索结果。错误详情: {'; '.join(errors)}"
    )
