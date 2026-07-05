# zero2oneAgent —— 从零实现的最小 Agent

## 快速开始

所有的命令建议在项目根目录下执行：

```bash
# 1. 安装依赖
pip install -r Agent/requirements.txt

# 2. 配置 API Key 与网络代理
# 复制模板文件为 .env
cp Agent/src/.env.example Agent/src/.env
# 编辑 Agent/src/.env，填入您的 LLM API Key (如阿里云 Maas) 
# 并按需配置 HTTP_PROXY（例如 http://127.0.0.1:7892）以启用免 Key 网页搜索

# 3. 运行 Agent CLI
python Agent/src/main.py

# 或指定 session 恢复之前的对话
python Agent/src/main.py --session my_session

# 4. 运行全量测试 (在 Windows 终端下推荐加上 -X utf8 避免 Emoji 编码错误)
python -X utf8 Agent/test/test_agent.py
```

## 系统设计

### 整体架构

```
用户输入
   │
   ▼
┌──────────┐     ┌───────────────┐     ┌──────────────┐
│  main.py │────▶│  AgentLoop    │────▶│  LLMClient   │
│  (CLI)   │     │  (loop.py)    │     │  (llm.py)    │
└──────────┘     └───────┬───────┘     └──────────────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌──────────┐ ┌────────┐ ┌────────┐
        │ Session  │ │Context │ │ Tool   │
        │ Manager  │ │Manager │ │Registry│
        └──────────┘ └────────┘ └───┬────┘
                                    │
                         ┌──────────┼──────────┐
                         ▼          ▼          ▼
                    calculator   search     weather
                                           todo
```

### 各模块职责

| 模块 | 文件 | 说明 |
|------|------|------|
| CLI 入口 | `main.py` | 终端交互、命令处理、组件初始化 |
| Agent 主循环 | `loop.py` | 核心 ReAct 循环：接收输入→LLM决策→执行工具→返回结果 |
| LLM 封装 | `llm.py` | OpenAI 兼容接口的薄封装 |
| 工具注册 | `tool_registry.py` | 工具的注册、schema 管理、执行路由、trace 记录 |
| Session | `session.py` | 多 session 管理、JSON 持久化 |
| Context | `context.py` | 历史消息构建、截断、压缩 |
| 配置 | `config.py` | 统一管理环境变量和默认值 |
| 日志 | `logger.py` | 双输出日志（文件+控制台） |

### Agent Loop 流程

```
while step < max_loop_steps:
    1. 从 session.messages 构建 LLM context
       - 加上 system prompt
       - 做轮次截断和失败记录清理
    
    2. 调用 LLM (带 tool schemas)
    
    3. 检查 LLM 响应:
       ├─ 没有 tool_calls → 直接返回文本回复，退出循环
       └─ 有 tool_calls  → 执行工具，把结果塞回 messages，继续循环
```

这个设计参考了 KDD starter-kit 的 ReAct 循环（`react.py`）和 Claude Code 的 `query.ts`。
区别在于，我用的是 OpenAI 的 function calling 机制，而不是让 LLM 输出 JSON 再自己解析，
function calling 更稳定，不用处理格式错误和 JSON repair。

### 工具系统

每个工具由两部分组成：
- **ToolSpec**: 静态描述（name, description, parameters JSON Schema）
- **Handler**: 执行函数，接收参数 dict，返回 ToolResult

```python
# 例子：calculator 工具的注册
SPEC = ToolSpec(
    name="calculator",
    description="计算数学表达式",
    parameters={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "数学表达式"}
        },
        "required": ["expression"]
    }
)

def handler(args: dict) -> ToolResult:
    expr = args["expression"]
    result = eval(expr, {"__builtins__": {}}, SAFE_NAMES)
    return ToolResult(ok=True, output=str(result))

# 注册
registry.register(SPEC, handler)
```

ToolRegistry 的 `get_tools_for_llm()` 方法会把所有注册的 ToolSpec 转成 OpenAI function calling
格式，LLM 根据这些 schema 自主决定是否调用工具、调用哪个。

当前实现了 4 个工具：

| 工具 | 类型 | 说明 |
|------|------|------|
| calculator | 无状态 | 安全的数学表达式计算（白名单 eval） |
| search | 无状态 | 免 Key 真实联网搜索（优先使用代理通过 DuckDuckGo 网页检索，自动降级为 Wikipedia 百科搜索） |
| weather | 无状态 | 实时天气查询（调用 wttr.in 免费 API 获取全球实时气象信息，免 Key） |
| todo | 有状态 | 待办事项管理，支持 add/list/done/delete，数据在 Session 级别隔离 |

### Session 管理

Session 是对话上下文的容器。要点：
- 每个 session 有独立的 `session_id` 和 `messages` 列表
- 不同 session 之间完全隔离（消息、todo 数据都各自独立）
- 持久化到磁盘上的 JSON 文件（`sessions/<session_id>.json`）
- 启动时自动加载已有 session，退出时自动保存

用法示例：
```
You > /new            # 创建新 session
You > /switch abc123  # 切换到指定 session
You > /list           # 列出所有 session
```

### Context 管理（Memory 的召回时机与放置方式）

**哪些信息塞入 context：**
- System prompt（固定在最前面，每次都带）
- 用户输入（完整保留）
- LLM 回复（完整保留）
- 工具调用的参数和返回结果（完整保留）
- 被截断的历史 → 用一条 system 消息标注"前面还有 N 条消息已省略"

**什么时候触发压缩/裁剪：**
1. **每次 LLM 调用前**：`build_messages_for_llm()` 做轮次截断
   - 超过 `max_turns` 时只保留最近的消息
   - 确保截断不会切在 tool_call 和 tool_result 中间
2. **每次用户输入后**：检查 `compress_threshold`
   - 超过阈值时调用 `compress_history()` 对早期对话做 LLM 摘要

**压缩策略：**
- 最近 8 条消息原样保留（保证追问有上下文）
- 更早的消息让 LLM 生成一段简要摘要
- 摘要放在 system message 里，作为上下文的一部分
- 连续失败的工具调用只保留最后一条（成功后更前面的失败就没意义了）

这个思路来自 `answer_docs.md` 里的分析：
> 去掉失败的 loop...比如调用工具失败了几次，最后成功了，完全可以在成功后把这些失败的 loop 去掉

### 异常处理

- LLM 调用失败：捕获异常，返回友好的错误提示给用户
- 工具参数解析失败（JSON decode error）：记日志，传空参数继续执行
- 工具执行异常：捕获 Exception，返回 ToolResult(ok=False)
- 循环超时：`max_loop_steps` 硬上限，到达后强制返回
- Session 加载失败：跳过损坏的文件，不影响其他 session

### 工具调用 Trace

每次工具调用都会记录一条 trace，包含：
- 工具名称
- 传入参数
- 执行结果（ok/error）
- 耗时
- 时间戳

通过 `/trace` 命令查看，或在日志文件（`logs/agent.log`）中查看。

## 目录结构

```
Agent/
├── src/
│   ├── main.py             # CLI 入口
│   ├── loop.py             # Agent 主循环
│   ├── llm.py              # LLM API 封装
│   ├── config.py           # 配置管理
│   ├── context.py          # Context 管理（截断/压缩）
│   ├── session.py          # Session 管理（多窗口隔离）
│   ├── tool_registry.py    # 工具注册表
│   ├── logger.py           # 日志配置
│   ├── .env                # 环境变量（不提交到 git）
│   ├── .env.example        # 环境变量模板
│   ├── globalPrompts/
│   │   └── rules.txt       # System Prompt
│   └── tools/
│       ├── calculator.py   # 计算器工具
│       ├── search.py       # 联网搜索工具（DDG+Wiki）
│       ├── weather.py      # 天气查询工具（wttr.in 实时）
│       └── todo.py         # 待办工具（有状态）
├── test/
│   └── test_agent.py       # 测试用例
├── requirements.txt
└── readme.md               # 本文档
```

## 设计决策记录

**1. 为什么用 function calling 而不是让 LLM 输出 JSON？**

如果让 LLM 输出 JSON 格式（thought/action/action_input），然后自己解析。
这种方式需要处理很多边界情况：JSON 格式错误、markdown 代码块包裹、换行符转义等。
OpenAI 的 function calling 把这些工作交给了 API 层，LLM 直接输出结构化的 tool_calls，
不用自己写解析器，也不用担心格式问题。

**2. 为什么不用数据库存 Session？**

对于这个 demo 的规模，JSON 文件足够了。好处是：
- 人工可读、可编辑、方便调试
- 不引入额外依赖
- 实现简单

**3. 工具为什么分 Spec 和 Handler？**

ToolSpec + handler 分离模式。好处是：
- Spec 是纯数据，可以序列化、传给 LLM
- Handler 是函数，可以有闭包（比如 todo 的 session_id 绑定）
- 注册时把两者关联起来，解耦清晰

**4. Context 压缩为什么这么简单？**

题目说了"复杂的压缩不用在这里实现"。当前做了两件事就够了：
- 轮次截断（超过 max_turns 只保留最近的）
- 失败记录清理（连续错误只保留最后一条）
- 可选的 LLM 摘要压缩（当对话超过阈值时）

更复杂的方案（比如基于 embedding 的语义记忆召回、层级记忆）在 answer_docs.md 里讨论了，
但这里不需要实现。

## AI Prompt 与问题解决记录

开发过程中让ai参考了我之前的项目agent的代码，做了一些复用：

1. **KDD starter-kit**（`kdd/starter-kit/`）
   - 工具注册模式：`ToolSpec` dataclass + `ToolRegistry`
   - ReAct 循环：`react.py` 的 while 循环结构
   - 历史压缩：连续失败折叠逻辑
   - Prompt 结构：system prompt + tool description + 对话历史
