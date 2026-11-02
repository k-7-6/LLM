import re

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Markdown, Static

from core.agent import Agent
from core.events import Completed, Token, ToolFinished, ToolStarted
from core.tools import catalog

TOOL_LABELS = {
    "getdate": "查询日期时间",
    "isleapyear": "判断闰年",
    "get_cwd": "查看当前目录",
    "list_dir": "列出目录内容",
    "get_file_type": "查看文件类型",
    "read_file": "读取文件",
    "create_file": "创建文件",
    "edit_file": "修改文件",
    "create_dir": "创建目录",
    "delete_dir": "删除目录",
    "delete_file": "删除文件",
    "rename": "重命名",
    "searchWeb": "联网搜索",
    "fetchWeb": "读取网页",
    "RunCli": "运行命令行",
    "loadSkill": "加载技能",
    "createSkill": "创建技能",
}

SUGGESTIONS = (
    ("查一下今天日期", "今天是几号？现在几点？"),
    ("看看项目文件", "列出当前项目目录下的文件，并简要介绍这个项目"),
    ("创建一个技能", "帮我创建一个新的技能，用来把一段文字翻译成英文"),
)

MCP_PREFIX = re.compile(r"^\[MCP:([^\]]+)\]\s*")


class ChatApp(App):
    """DeepSeek 风格的深色聊天界面。"""

    TITLE = "ZAgent"
    SUB_TITLE = "智能助手"
    ENABLE_COMMAND_PALETTE = False  # 关闭内置英文命令面板（Ctrl+P）

    CSS = """
    Screen {
        background: #212121;
        color: #ececec;
        scrollbar-color: #3a3a3a;
        scrollbar-color-hover: #4d6bfe;
        scrollbar-color-active: #4d6bfe;
        scrollbar-background: #212121;
        scrollbar-size-vertical: 1;
    }

    #topbar {
        height: 3;
        background: #171717;
        border-bottom: solid #2e2e2e;
        padding: 0 2;
    }
    #brand {
        width: 1fr;
        content-align: left middle;
        text-style: bold;
        color: #ececec;
    }
    #tagline {
        width: auto;
        content-align: right middle;
        color: #6f6f6f;
    }

    #body { height: 1fr; }
    #main { width: 1fr; height: 1fr; }
    #log {
        width: 1fr;
        height: 1fr;
        padding: 1 3;
        align: center top;
        scrollbar-color: #3a3a3a;
        scrollbar-color-hover: #4d6bfe;
        scrollbar-color-active: #4d6bfe;
        scrollbar-background: #212121;
    }
    #sidebar {
        width: 40;
        height: 1fr;
        background: #171717;
        border-left: solid #2e2e2e;
        padding: 1;
        scrollbar-color: #3a3a3a;
        scrollbar-color-hover: #4d6bfe;
        scrollbar-color-active: #4d6bfe;
        scrollbar-background: #171717;
    }

    .welcome {
        width: 1fr;
        max-width: 100;
        height: auto;
        padding: 3 2 1 2;
        align: center top;
    }
    .welcome-mark {
        width: 1fr;
        text-align: center;
        color: #4d6bfe;
        text-style: bold;
    }
    .welcome-title {
        width: 1fr;
        text-align: center;
        text-style: bold;
        color: #f2f2f2;
        margin-top: 1;
    }
    .welcome-sub {
        width: 1fr;
        text-align: center;
        color: #8b8b8b;
        margin-top: 1;
    }
    .welcome-status {
        width: 1fr;
        text-align: center;
        color: #6f6f6f;
        margin-top: 1;
    }
    .welcome-error {
        width: 1fr;
        text-align: center;
        color: #ff7b7b;
        margin-top: 1;
    }

    #suggestions {
        width: 1fr;
        height: auto;
        align: center middle;
        margin-top: 2;
    }
    #suggestions Button {
        width: auto;
        min-width: 0;
        height: 3;
        margin: 0 1;
        padding: 0 2;
        background: #2a2a2a;
        color: #d6d6d6;
        border: round #3a3a3a;
    }
    #suggestions.stacked Button {
        width: 30;
        margin: 0 0 1 0;
    }
    #suggestions Button:hover {
        background: #333333;
        color: #f2f2f2;
        border: round #4d6bfe;
    }

    .user-row {
        width: 1fr;
        max-width: 100;
        height: auto;
        align: right top;
        padding: 1 0 0 6;
    }
    .user-bubble {
        width: auto;
        max-width: 80%;
        background: #303030;
        color: #f0f0f0;
        border: round #3d3d3d;
        padding: 1 2;
    }

    .assistant-row {
        width: 1fr;
        max-width: 100;
        height: auto;
        padding: 1 0 0 0;
    }
    .avatar {
        width: 3;
        height: auto;
        color: #4d6bfe;
        text-style: bold;
        padding: 0 0 0 1;
    }
    .assistant-content {
        width: 1fr;
        height: auto;
        color: #ececec;
        padding: 0 1;
    }
    .assistant-md {
        width: 1fr;
        height: auto;
        padding: 0 1;
        background: transparent;
    }

    .tool-row {
        width: 1fr;
        max-width: 100;
        height: auto;
        padding: 1 0 0 4;
    }
    .tool-pill {
        width: auto;
        background: #262626;
        color: #9a9a9a;
        border: round #363636;
        padding: 0 1;
    }
    .error-pill {
        width: auto;
        background: #3a2222;
        color: #ff8a8a;
        border: round #5a3030;
        padding: 0 1;
    }

    #composer {
        height: auto;
        padding: 0 3 1 3;
        background: #212121;
        border-top: solid #2e2e2e;
        align: center top;
    }
    #prompt {
        width: 1fr;
        max-width: 100;
        height: 3;
        margin: 1 0 0 0;
        padding: 0 1;
        border: round #3a3a3a;
        background: #2b2b2b;
        color: #f0f0f0;
    }
    #prompt:focus {
        border: round #4d6bfe;
        background: #2f2f2f;
    }
    #hint {
        width: 1fr;
        max-width: 100;
        height: 1;
        text-align: center;
        color: #6f6f6f;
    }
    """

    BINDINGS = [("ctrl+c", "quit", "退出")]

    def __init__(self, agent: Agent):
        super().__init__()
        self.agent = agent
        self._answer: Static | None = None
        self._answer_row: Horizontal | None = None
        self._answer_text = ""
        self._tool_pill: Static | None = None
        self._tool_label = ""
        self._busy = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static(
                Text.assemble(("◈ ", "#4d6bfe"), ("ZAgent", "bold #ececec")),
                id="brand",
            )
            yield Static("本地智能助手", id="tagline")
        with Horizontal(id="body"):
            with Vertical(id="main"):
                yield VerticalScroll(id="log")
                with Vertical(id="composer"):
                    yield Input(placeholder="给 ZAgent 发送消息…", id="prompt")
                    yield Static("Enter 发送 · Ctrl+C 退出", id="hint")
            yield VerticalScroll(self._sidebar(), id="sidebar")

    def _sidebar(self) -> Static:
        """右侧常驻面板：按本地工具、MCP 工具、技能分组。"""
        text = Text()
        tools = catalog()
        local: list = []
        remote: dict[str, list[str]] = {}
        for tool in tools:
            match = MCP_PREFIX.match(tool.description)
            if match:
                remote.setdefault(match.group(1), []).append(tool.name)
            else:
                local.append(tool)

        text.append("本地工具", style="bold #f2f2f2")
        text.append(f"  {len(local)}", style="#4d6bfe")
        text.append("\n\n")
        for index, tool in enumerate(local, 1):
            label = TOOL_LABELS.get(tool.name, tool.name)
            text.append(f"{index:>2}  ", style="#5a5a5a")
            text.append(f"{label}\n", style="#dcdcdc")

        if remote:
            text.append("\nMCP 工具", style="bold #f2f2f2")
            text.append(f"  {sum(len(v) for v in remote.values())}", style="#4d6bfe")
            text.append("\n\n")
            for server, names in remote.items():
                text.append(f"{server}\n", style="#4d6bfe")
                for name in names:
                    text.append(f"  · {name}\n", style="#dcdcdc")

        text.append("\n技能", style="bold #f2f2f2")
        text.append(f"  {len(self.agent.skills)}", style="#4d6bfe")
        text.append("\n\n")
        if self.agent.skills:
            for skill in self.agent.skills:
                text.append(f"· {skill.name}\n", style="#dcdcdc")
        else:
            text.append("· 未发现技能\n", style="#6f6f6f")
        return Static(text)

    def action_help_quit(self) -> None:
        """覆盖框架默认的 Ctrl+C 英文提示，直接退出。"""
        self.exit()

    def on_mount(self) -> None:
        self.query_one("#log", VerticalScroll).mount(self._welcome())
        self.query_one("#prompt", Input).focus()

    def _welcome(self) -> Vertical:
        children = [
            Static(Text("◈"), classes="welcome-mark"),
            Static(Text("我是 ZAgent"), classes="welcome-title"),
            Static(
                Text("很高兴见到你！可以问我问题，也可以让我查资料、读文件、执行命令。"),
                classes="welcome-sub",
            ),
            self._suggestions(),
        ]
        if self.agent.skills:
            children.append(Static(
                Text(f"已加载 {len(self.agent.skills)} 个技能"),
                classes="welcome-status",
            ))
        else:
            children.append(Static(
                Text("未发现技能 · 请从包含 .agents/skills 的项目目录启动"),
                classes="welcome-status",
            ))
        for message in self.agent.mcp_errors:
            children.append(Static(
                Text(f"MCP · {message}"),
                classes="welcome-error",
            ))
        return Vertical(*children, id="welcome", classes="welcome")

    def _suggestions(self) -> Horizontal | Vertical:
        """宽屏横向排列，窄屏纵向堆叠，避免按钮溢出。"""
        buttons = [
            Button(label, id=f"suggest-{index}")
            for index, (label, _prompt) in enumerate(SUGGESTIONS)
        ]
        if self.size.width >= 112:
            return Horizontal(*buttons, id="suggestions")
        return Vertical(*buttons, id="suggestions", classes="stacked")

    @on(Button.Pressed)
    def _pick_suggestion(self, event: Button.Pressed) -> None:
        if not event.button.id or not event.button.id.startswith("suggest-"):
            return
        index = int(event.button.id.removeprefix("suggest-"))
        self._send(SUGGESTIONS[index][1])

    @on(Input.Submitted)
    def _submit(self, event: Input.Submitted) -> None:
        self._send(event.value)

    def _send(self, text: str) -> None:
        text = text.strip()
        if not text or self._busy:
            return
        self._busy = True
        self._remove_welcome()

        prompt = self.query_one("#prompt", Input)
        prompt.value = ""
        prompt.disabled = True

        log = self.query_one("#log", VerticalScroll)
        log.mount(Horizontal(
            Static(Text(text), classes="user-bubble"),
            classes="user-row",
        ))
        log.scroll_end(animate=False)

        self._answer = None
        self._answer_row = None
        self._answer_text = ""
        self._tool_pill = None
        self._stream(text)

    def _remove_welcome(self) -> None:
        for widget in self.query("#welcome"):
            widget.remove()

    @work(thread=True, exclusive=True)
    def _stream(self, text: str) -> None:
        try:
            for event in self.agent.ask(text):
                if isinstance(event, Token):
                    self.call_from_thread(self._append, event.text)
                elif isinstance(event, ToolStarted):
                    self.call_from_thread(self._show_tool, event.name)
                elif isinstance(event, ToolFinished):
                    self.call_from_thread(self._finish_tool)
                elif isinstance(event, Completed):
                    self.call_from_thread(self._finish_answer, event.text)
        except Exception as exc:
            self.call_from_thread(self._show_error, exc)
        finally:
            self.call_from_thread(self._done)

    def _append(self, text: str) -> None:
        """流式追加文本；工具调用之后会另起一条助手消息。"""
        if self._answer is None:
            self._answer_text = ""
            self._answer = Static(Text(""), classes="assistant-content")
            self._answer_row = Horizontal(
                Static(Text("✦"), classes="avatar"),
                self._answer,
                classes="assistant-row",
            )
            self.query_one("#log", VerticalScroll).mount(self._answer_row)
        self._answer_text += text
        self._answer.update(Text(self._answer_text))
        self._scroll()

    def _finish_answer(self, text: str) -> None:
        """流式结束后用 Markdown 重新渲染，保留标题、列表和代码块样式。"""
        if not text.strip() or self._answer is None or self._answer_row is None:
            return
        row = self._answer_row
        content = self._answer
        self._answer = None
        self._answer_row = None
        self._answer_text = ""
        row.mount(Markdown(text, classes="assistant-md"))
        content.remove()
        self._scroll()

    def _show_tool(self, name: str) -> None:
        self._answer = None
        self._answer_row = None
        self._answer_text = ""
        self._tool_label = TOOL_LABELS.get(name, name)
        pill = Static(
            Text(f"⚙ 正在调用 · {self._tool_label}"),
            classes="tool-pill",
        )
        self._tool_pill = pill
        self.query_one("#log", VerticalScroll).mount(
            Horizontal(pill, classes="tool-row"),
        )
        self._scroll()

    def _finish_tool(self) -> None:
        if self._tool_pill is None:
            return
        self._tool_pill.update(Text(
            f"✓ {self._tool_label} 完成",
            style="#7fbf8a",
        ))
        self._tool_pill = None
        self._scroll()

    def _show_error(self, exc: Exception) -> None:
        self.query_one("#log", VerticalScroll).mount(Horizontal(
            Static(Text(f"错误 · {exc}"), classes="error-pill"),
            classes="tool-row",
        ))
        self._scroll()

    def _scroll(self) -> None:
        self.query_one("#log", VerticalScroll).scroll_end(animate=False)

    def _done(self) -> None:
        self._busy = False
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
        prompt.focus()
        self._scroll()
