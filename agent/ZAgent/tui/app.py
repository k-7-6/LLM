import re
import threading

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Markdown, Static

from core.agent import Agent
from core.context import (
    CompactionResult,
    ContextStats,
    read_archive,
    render_transcript,
)
from core.events import (
    Cancelled,
    Completed,
    Token,
    ToolFinished,
    ToolStarted,
    TurnUsage,
)
from core.mcp import (
    STATUS_CLOSED,
    STATUS_CONNECTED,
    STATUS_CONNECTING,
    STATUS_FAILED,
    McpSnapshot,
)
from core.tools import catalog
from tui.commands import (
    SLASH_COMMANDS,
    exact as exact_command,
    matches as match_commands,
)
from tui.compact_log import CompactLogScreen
from tui.config_notice import ConfigNoticeScreen
from tui.session_panel import ResumeScreen

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
    "recallContext": "检索历史上下文",
}

SUGGESTIONS = (
    ("查一下今天日期", "今天是几号？现在几点？"),
    ("看看项目文件", "列出当前项目目录下的文件，并简要介绍这个项目"),
    ("创建一个技能", "帮我创建一个新的技能，用来把一段文字翻译成英文"),
)

MCP_PREFIX = re.compile(r"^\[MCP:([^\]]+)\]\s*")


class PromptInput(Input):
    """输入框：斜杠命令面板可见时优先处理上下键、Tab 和 Esc。"""

    def on_key(self, event) -> None:
        handler = getattr(self.app, "handle_palette_key", None)
        if handler is not None and handler(event.key):
            event.prevent_default()
            event.stop()


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
    #context {
        width: auto;
        content-align: right middle;
        color: #8b8b8b;
        margin-left: 2;
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
    #sidebar-content {
        width: 1fr;
        height: auto;
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

    .suggestions {
        width: 1fr;
        height: auto;
        align: center middle;
        margin-top: 2;
    }
    .suggestions Button {
        width: auto;
        min-width: 0;
        height: 3;
        margin: 0 1;
        padding: 0 2;
        background: #2a2a2a;
        color: #d6d6d6;
        border: round #3a3a3a;
    }
    .suggestions.stacked Button {
        width: 30;
        margin: 0 0 1 0;
    }
    .suggestions Button:hover {
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
    .usage-row {
        width: 1fr;
        max-width: 100;
        height: auto;
        padding: 0 0 0 4;
    }
    .usage-pill {
        width: auto;
        color: #6f6f6f;
        padding: 0 1;
    }
    .stopped-pill {
        width: auto;
        background: #332b1f;
        color: #ffb86b;
        border: round #55452a;
        padding: 0 1;
    }

    .notice-row {
        width: 1fr;
        max-width: 100;
        height: auto;
        padding: 1 0 0 4;
    }
    .context-warning {
        width: 1fr;
        background: #3a2f1f;
        color: #ffb86b;
        border: round #5a4728;
        padding: 0 1;
    }
    .context-info {
        width: 1fr;
        background: #1f2f24;
        color: #8fd19e;
        border: round #2f4a36;
        padding: 0 1;
    }
    .context-error {
        width: 1fr;
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
    #palette {
        width: 1fr;
        max-width: 100;
        height: auto;
        margin: 1 0 0 0;
        padding: 0 1;
        background: #1f1f1f;
        border: round #3a3a3a;
        display: none;
    }
    #palette.visible {
        display: block;
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
    #statusline {
        width: 1fr;
        max-width: 100;
        height: 1;
    }
    #status {
        width: auto;
        content-align: left middle;
        color: #8b8b8b;
        margin-right: 1;
    }
    #model-label {
        width: 1fr;
        content-align: left middle;
        color: #8b8b8b;
    }
    #hint {
        width: auto;
        content-align: right middle;
        color: #6f6f6f;
    }
    """

    BINDINGS = [
        ("ctrl+c", "save_quit", "退出"),
        ("escape", "stop", "停止输出"),
    ]

    def __init__(self, agent: Agent, config_notice: str | None = None):
        super().__init__()
        self.agent = agent
        self.config_notice = config_notice
        self._answer: Static | None = None
        self._answer_row: Horizontal | None = None
        self._answer_text = ""
        self._tool_pill: Static | None = None
        self._tool_label = ""
        self._busy = False
        self._cancellable = False
        self._stop_requested = False
        self._stop_event: threading.Event | None = None
        self._pre_compact_stats: ContextStats | None = None
        self._context_warned = False
        self._ui_ready = False
        self._mcp_state: McpSnapshot | None = None

        # 斜杠命令补全面板
        self._palette_visible = False
        self._palette_matches: list = []
        self._palette_index = 0
        self._suppress_palette = False
        # 重建欢迎页时用于避免旧组件尚未移除造成的重复 ID。
        self._view_serial = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static(
                Text.assemble(("◈ ", "#4d6bfe"), ("ZAgent", "bold #ececec")),
                id="brand",
            )
            yield Static("本地智能助手", id="tagline")
            yield Static("", id="context")
        with Horizontal(id="body"):
            with Vertical(id="main"):
                yield VerticalScroll(id="log")
                with Vertical(id="composer"):
                    yield Static("", id="palette")
                    yield PromptInput(
                        placeholder="给 ZAgent 发送消息…（输入 / 查看命令）",
                        id="prompt",
                    )
                    with Horizontal(id="statusline"):
                        yield Static("", id="status")
                        yield Static(
                            f"模型 {getattr(self.agent, 'model', '未知')}",
                            id="model-label",
                        )
                        yield Static("Enter 发送 · / 命令 · Ctrl+C 退出", id="hint")
            with VerticalScroll(id="sidebar"):
                yield Static("", id="sidebar-content")

    def _refresh_sidebar(self) -> None:
        """右侧常驻面板：本地工具、MCP 服务器/工具、技能与会话。"""
        text = Text()
        tools = catalog()
        local: list = []
        for tool in tools:
            if not MCP_PREFIX.match(tool.description):
                local.append(tool)

        text.append("本地工具", style="bold #f2f2f2")
        text.append(f"  {len(local)}", style="#4d6bfe")
        text.append("\n\n")
        for index, tool in enumerate(local, 1):
            label = TOOL_LABELS.get(tool.name, tool.name)
            text.append(f"{index:>2}  ", style="#5a5a5a")
            text.append(f"{label}\n", style="#dcdcdc")

        snapshot = self._mcp_state or self.agent.mcp_snapshot()
        self._mcp_state = snapshot
        text.append("\nMCP 服务器", style="bold #f2f2f2")
        if snapshot.servers:
            text.append(
                f"  {snapshot.connected_count}/{len(snapshot.servers)}",
                style="#4d6bfe",
            )
        text.append("\n\n")
        if not snapshot.configured and not snapshot.servers:
            text.append("· 未找到 .mcp.json\n", style="#6f6f6f")
        elif snapshot.configured and not snapshot.servers and not snapshot.errors:
            text.append("· 未配置服务器\n", style="#6f6f6f")
        elif snapshot.loading:
            text.append("◌ 正在连接…\n", style="#ffb86b")
        for server in snapshot.servers:
            if server.status == STATUS_CONNECTED:
                text.append("● ", style="#7fbf8a")
                text.append(f"{server.name}\n", style="#dcdcdc")
                for name in server.tools:
                    text.append(f"  · {name}\n", style="#8b8b8b")
                if not server.tools:
                    text.append("  · 无可用工具\n", style="#6f6f6f")
            elif server.status == STATUS_CONNECTING:
                text.append("◌ ", style="#ffb86b")
                text.append(f"{server.name} 连接中…\n", style="#8b8b8b")
            elif server.status == STATUS_CLOSED:
                text.append("○ ", style="#6f6f6f")
                text.append(f"{server.name} 已断开\n", style="#6f6f6f")
            else:
                text.append("✗ ", style="#ff8a8a")
                text.append(f"{server.name}\n", style="#ff8a8a")
                error = (server.error or "连接失败").strip()
                if len(error) > 160:
                    error = error[:159] + "…"
                text.append(f"  {error}\n", style="#a86b6b")
        server_errors = tuple(item.error or "" for item in snapshot.servers)
        for error in snapshot.errors:
            if any(error in existing for existing in server_errors):
                continue
            text.append(f"· {error}\n", style="#ff8a8a")

        text.append("\n技能", style="bold #f2f2f2")
        text.append(f"  {len(self.agent.skills)}", style="#4d6bfe")
        text.append("\n\n")
        if self.agent.skills:
            for skill in self.agent.skills:
                text.append(f"· {skill.name}\n", style="#dcdcdc")
        else:
            text.append("· 未发现技能\n", style="#6f6f6f")

        text.append("\n会话", style="bold #f2f2f2")
        text.append("\n\n")
        info = self.agent.current_session()
        if info is None:
            text.append("· 尚未创建\n", style="#6f6f6f")
        else:
            text.append(f"· {info.id}\n", style="#dcdcdc")
            text.append(f"  {info.messages} 条消息\n", style="#8b8b8b")
        if self.agent.agents_md_active:
            text.append(f"· AGENTS.md 已注入\n", style="#7fbf8a")
        else:
            text.append("· 未注入 AGENTS.md\n", style="#6f6f6f")

        try:
            self.query_one("#sidebar-content", Static).update(text)
        except Exception:
            pass

    def action_save_quit(self) -> None:
        """Ctrl+C：保存当前会话并退出。"""
        self._save_and_exit()

    def _save_and_exit(self) -> None:
        if self._busy:
            self._stop_requested = True
            if self._stop_event is not None:
                self._stop_event.set()
            self.agent.cancel()
        try:
            self.agent.save_session()
        except Exception:
            pass
        self.agent.set_mcp_listener(None)
        self.exit()

    def on_mount(self) -> None:
        self._set_status("就绪", "#8b8b8b", "#7fbf8a")
        self._refresh_model_label()
        self.query_one("#log", VerticalScroll).mount(self._welcome())
        self._ui_ready = True
        self._update_context(self.agent.context_stats())
        self.query_one("#prompt", Input).focus()

        self.agent.set_mcp_listener(self._mcp_updated)
        self._apply_mcp_snapshot(self.agent.mcp_snapshot())
        if self.config_notice:
            self.push_screen(
                ConfigNoticeScreen(self.config_notice),
                self._config_notice_closed,
            )

    def on_unmount(self) -> None:
        self.agent.set_mcp_listener(None)

    def _config_notice_closed(self, _result=None) -> None:
        self.exit()

    def _mcp_updated(self, snapshot: McpSnapshot) -> None:
        """MCP 后台线程回调：切回 UI 线程刷新边栏。"""
        try:
            self.call_from_thread(self._apply_mcp_snapshot, snapshot)
        except Exception:
            # 可能回调来自 UI 线程，或界面正在退出。
            try:
                self._apply_mcp_snapshot(snapshot)
            except Exception:
                pass

    def _apply_mcp_snapshot(self, snapshot: McpSnapshot) -> None:
        self._mcp_state = snapshot
        if self._ui_ready:
            self._refresh_sidebar()
            try:
                self._update_context(self.agent.context_stats())
            except Exception:
                pass

    def on_resize(self, event) -> None:
        if not self._ui_ready:
            return
        self._refresh_model_label()
        self._update_context(self.agent.context_stats())

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
                Text(f"已加载 {len(self.agent.skills)} 个技能 · 输入 / 查看命令"),
                classes="welcome-status",
            ))
        else:
            children.append(Static(
                Text("未发现技能 · 输入 / 查看命令"),
                classes="welcome-status",
            ))
        for message in self.agent.mcp_errors:
            children.append(Static(
                Text(f"MCP · {message}"),
                classes="welcome-error",
            ))
        return Vertical(
            *children,
            id=f"welcome-{self._view_serial}",
            classes="welcome",
        )

    def _suggestions(self) -> Horizontal | Vertical:
        """宽屏横向排列，窄屏纵向堆叠，避免按钮溢出。"""
        buttons = [
            Button(label, id=f"suggest-{self._view_serial}-{index}")
            for index, (label, _prompt) in enumerate(SUGGESTIONS)
        ]
        if self.size.width >= 112:
            return Horizontal(*buttons, id=f"suggestions-{self._view_serial}",
                              classes="suggestions")
        return Vertical(*buttons, id=f"suggestions-{self._view_serial}",
                        classes="suggestions stacked")

    @on(Button.Pressed)
    def _pick_suggestion(self, event: Button.Pressed) -> None:
        if not event.button.id or not event.button.id.startswith("suggest-"):
            return
        try:
            index = int(event.button.id.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            return
        self._send(SUGGESTIONS[index][1])

    # ---------- 斜杠命令补全 ----------

    @on(Input.Changed)
    def _prompt_changed(self, event: Input.Changed) -> None:
        if self._suppress_palette:
            return
        self._update_palette(event.value)

    def _update_palette(self, value: str) -> None:
        found = match_commands(value)
        if not found:
            self._hide_palette()
            return
        self._palette_matches = list(found)
        self._palette_index = min(
            self._palette_index, len(self._palette_matches) - 1,
        )
        if self._palette_index < 0:
            self._palette_index = 0
        self._palette_visible = True
        self._render_palette()

    def _render_palette(self) -> None:
        try:
            palette = self.query_one("#palette", Static)
        except Exception:
            return
        if not self._palette_visible:
            palette.remove_class("visible")
            return
        text = Text()
        for index, command in enumerate(self._palette_matches):
            selected = index == self._palette_index
            text.append("▸ " if selected else "  ",
                        style="#4d6bfe" if selected else "#5a5a5a")
            text.append(
                f"{command.name:<10}",
                style="bold #7d97ff" if selected else "#dcdcdc",
            )
            text.append(command.description,
                        style="#dcdcdc" if selected else "#8b8b8b")
            text.append("\n")
        text.append(
            "↑↓ 选择 · Tab 补全 · Enter 执行 · Esc 关闭",
            style="#5a5a5a",
        )
        palette.update(text)
        palette.add_class("visible")

    def _hide_palette(self) -> None:
        self._palette_visible = False
        self._palette_matches = []
        self._palette_index = 0
        try:
            self.query_one("#palette", Static).remove_class("visible")
        except Exception:
            pass

    def _move_palette(self, delta: int) -> None:
        if not self._palette_matches:
            return
        self._palette_index = (
            self._palette_index + delta
        ) % len(self._palette_matches)
        self._render_palette()

    def _complete_palette(self) -> None:
        if not self._palette_matches:
            return
        command = self._palette_matches[self._palette_index]
        prompt = self.query_one("#prompt", PromptInput)
        self._suppress_palette = True
        try:
            prompt.value = command.name
            prompt.cursor_position = len(command.name)
        finally:
            self._suppress_palette = False
        self._palette_matches = list(match_commands(command.name))
        self._palette_index = 0
        self._palette_visible = True
        self._render_palette()
        prompt.focus()

    def handle_palette_key(self, key: str) -> bool:
        """输入框按键钩子；返回 True 表示已消费该按键。"""
        if not self._palette_visible:
            return False
        if key == "up":
            self._move_palette(-1)
            return True
        if key == "down":
            self._move_palette(1)
            return True
        if key == "tab":
            self._complete_palette()
            return True
        if key == "escape":
            self._hide_palette()
            return True
        return False

    def _clear_prompt(self) -> None:
        self._suppress_palette = True
        try:
            self.query_one("#prompt", PromptInput).value = ""
        finally:
            self._suppress_palette = False

    @on(Input.Submitted)
    def _submit(self, event: Input.Submitted) -> None:
        if self._dispatch_command(event.value):
            return
        self._send(event.value)

    def _dispatch_command(self, value: str) -> bool:
        """处理斜杠命令；不是命令时返回 False。"""
        text = (value or "").strip()
        if not text.startswith("/"):
            return False

        command = exact_command(text)
        if command is None and self._palette_visible and self._palette_matches:
            command = self._palette_matches[self._palette_index]
        if command is None:
            self._clear_prompt()
            self._hide_palette()
            self._notice(
                f"未知命令：{text.split(maxsplit=1)[0]}。输入 /help 查看可用命令。",
                "context-error",
            )
            return True

        self._clear_prompt()
        self._hide_palette()
        name = command.name

        if self._busy and name not in ("/status", "/help", "/mcp", "/quit"):
            self._notice(
                "当前任务正在执行，请等待完成后再切换或保存会话。",
                "context-warning",
            )
            return True

        if name == "/new":
            self._command_new()
        elif name == "/resume":
            self._command_resume(text)
        elif name == "/save":
            self._command_save()
        elif name == "/compact":
            self._start_compact()
        elif name == "/status":
            self._command_status()
        elif name == "/mcp":
            self._command_mcp()
        elif name == "/help":
            self._command_help()
        elif name == "/quit":
            self._save_and_exit()
        return True

    def _command_help(self) -> None:
        lines = ["可用斜杠命令：", ""]
        for command in SLASH_COMMANDS:
            lines.append(f"{command.name:<10} {command.description}")
        lines += ["", "输入 / 可随时打开补全面板；↑↓ 选择，Tab 补全，Enter 执行。"]
        self._notice("\n".join(lines), "context-info")

    def _command_status(self) -> None:
        info = self.agent.current_session()
        stats = self.agent.context_stats()
        snapshot = self.agent.mcp_snapshot()
        lines = ["当前状态：", ""]
        if info is None:
            lines.append("会话：尚未创建（发送第一条消息后自动创建）")
        else:
            lines.append(f"会话：{info.id} · {info.title}")
            lines.append(f"消息：{info.messages} 条")
        lines.append(
            f"上下文：{stats.used:,} / {stats.window:,} tokens"
            f"（{stats.percent:.1f}%）"
        )
        lines.append(
            "AGENTS.md：已注入 " + self.agent.agents_md_path
            if self.agent.agents_md_active else "AGENTS.md：未注入"
        )
        lines.append(
            f"MCP：{snapshot.connected_count}/{len(snapshot.servers)} 台服务器已连接，"
            f"{snapshot.tool_count} 个工具"
        )
        if self.agent.session_error:
            lines.append(f"会话写入错误：{self.agent.session_error}")
        self._notice("\n".join(lines), "context-info")

    def _command_mcp(self) -> None:
        snapshot = self.agent.mcp_snapshot()
        lines = [f"MCP 配置：{snapshot.config_path}", ""]
        if not snapshot.configured and not snapshot.servers:
            lines.append("未找到 .mcp.json。")
        if snapshot.loading:
            lines.append("正在连接…")
        for server in snapshot.servers:
            if server.status == STATUS_CONNECTED:
                lines.append(f"● {server.name} · 已连接")
                if server.tools:
                    for tool in server.tools:
                        lines.append(f"  · {tool}")
                else:
                    lines.append("  · 无可用工具")
            elif server.status == STATUS_CONNECTING:
                lines.append(f"◌ {server.name} · 连接中")
            elif server.status == STATUS_CLOSED:
                lines.append(f"○ {server.name} · 已断开")
            else:
                lines.append(f"✗ {server.name} · 连接失败")
                if server.error:
                    lines.append(f"  {server.error}")
        for error in snapshot.errors:
            if not any(error in (item.error or "") for item in snapshot.servers):
                lines.append(f"错误：{error}")
        if not snapshot.servers and not snapshot.errors:
            lines.append("没有配置任何 MCP 服务器。")
        self._notice("\n".join(lines), "context-info")

    def _command_save(self) -> None:
        info = self.agent.save_session()
        if info is None:
            self._notice(
                f"保存会话失败：{self.agent.session_error or '未知错误'}",
                "context-error",
            )
            return
        self._notice(
            f"已保存会话 {info.id} · {info.title} · {info.messages} 条消息。",
            "context-info",
        )
        self._refresh_sidebar()

    def _command_new(self) -> None:
        try:
            switch = self.agent.new_session()
        except Exception as exc:
            self._notice(f"新建会话失败：{exc}", "context-error")
            return
        self._reset_chat_view()
        saved = (
            f"已自动保存上一会话 {switch.saved.id}。"
            if switch.saved is not None else ""
        )
        agents = (
            f" 已注入 {self.agent.agents_md_path}。" if self.agent.agents_md_active
            else ""
        )
        self._notice(
            f"{saved}已新建会话 {switch.session.id}。{agents}".strip(),
            "context-info",
        )
        self._update_context(self.agent.context_stats())
        self._refresh_sidebar()
        self._refresh_hint()
        self.query_one("#prompt", PromptInput).focus()

    def _command_resume(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            self._resume_session_id(parts[1].strip())
            return
        sessions = self.agent.list_sessions()
        self.push_screen(ResumeScreen(sessions), self._resume_selected)

    def _resume_selected(self, session_id: str | None) -> None:
        if not session_id:
            return
        self._resume_session_id(session_id)

    def _resume_session_id(self, session_id: str) -> None:
        try:
            switch = self.agent.resume_session(session_id)
        except Exception as exc:
            self._notice(f"恢复会话失败：{exc}", "context-error")
            return
        if switch is None:
            self._notice(f"未找到会话 {session_id}。", "context-error")
            return
        self._render_session(switch)
        self._refresh_sidebar()

    def _reset_chat_view(self) -> None:
        log = self.query_one("#log", VerticalScroll)
        self._view_serial += 1
        for child in list(log.children):
            child.remove()
        log.mount(self._welcome())
        log.scroll_home(animate=False)
        self._answer = None
        self._answer_row = None
        self._answer_text = ""
        self._tool_pill = None

    def _render_session(self, switch) -> None:
        """把恢复的会话消息重新绘制到聊天区。"""
        self._reset_chat_view()
        if any(
            message.get("role") in ("user", "assistant", "tool")
            for message in self.agent.messages
        ):
            self._remove_welcome()
        saved = (
            f"已自动保存上一会话 {switch.saved.id}。"
            if switch.saved is not None else ""
        )
        self._notice(
            f"{saved}已恢复会话 {switch.session.id} · {switch.session.title}",
            "context-info",
        )
        log = self.query_one("#log", VerticalScroll)
        call_names: dict[str, str] = {}
        for message in self.agent.messages:
            role = message.get("role")
            content = message.get("content")
            if role == "user":
                if isinstance(content, str) and content.strip():
                    log.mount(Horizontal(
                        Static(Text(content), classes="user-bubble"),
                        classes="user-row",
                    ))
            elif role == "assistant":
                if isinstance(content, str) and content.strip():
                    log.mount(Horizontal(
                        Static(Text("✦"), classes="avatar"),
                        Markdown(content, classes="assistant-md"),
                        classes="assistant-row",
                    ))
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    name = str(function.get("name", ""))
                    call_id = str(call.get("id", ""))
                    if call_id:
                        call_names[call_id] = name
                    label = TOOL_LABELS.get(name, name or "工具")
                    log.mount(Horizontal(
                        Static(
                            Text(f"⚙ {label} · 历史调用"),
                            classes="tool-pill",
                        ),
                        classes="tool-row",
                    ))
            elif role == "tool":
                name = call_names.get(str(message.get("tool_call_id", "")), "")
                label = TOOL_LABELS.get(name, name or "工具")
                log.mount(Horizontal(
                    Static(
                        Text(f"✓ {label} · 历史结果"),
                        classes="tool-pill",
                    ),
                    classes="tool-row",
                ))
        log.scroll_end(animate=False)
        self._update_context(self.agent.context_stats())
        self._set_status("就绪", "#8b8b8b", "#7fbf8a")
        self._refresh_hint()

    def _send(self, text: str) -> None:
        text = text.strip()
        if not text or self._busy:
            return
        if text.startswith("/"):
            self._dispatch_command(text)
            return

        stats = self.agent.context_stats()
        if stats.blocked:
            self._clear_prompt()
            self._hide_palette()
            self._notice(
                f"上下文已使用 {stats.percent:.1f}%，请先输入 /compact 压缩上下文。",
                "context-warning",
            )
            return

        self._busy = True
        self._cancellable = True
        self._stop_requested = False
        self._stop_event = threading.Event()
        self._set_status("思考中…", "#4d6bfe")
        self._refresh_hint()
        self._remove_welcome()

        prompt = self.query_one("#prompt", PromptInput)
        self._clear_prompt()
        self._hide_palette()
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
        self._stream(text, self._stop_event)

    def _remove_welcome(self) -> None:
        for widget in self.query(".welcome"):
            widget.remove()

    @work(thread=True, exclusive=True)
    def _stream(self, text: str, stop_event: threading.Event) -> None:
        try:
            for event in self.agent.ask(text, cancel=stop_event):
                if isinstance(event, Token):
                    self.call_from_thread(self._append, event.text)
                elif isinstance(event, ToolStarted):
                    self.call_from_thread(self._show_tool, event.name)
                elif isinstance(event, ToolFinished):
                    self.call_from_thread(self._finish_tool)
                elif isinstance(event, ContextStats):
                    self.call_from_thread(self._update_context, event)
                elif isinstance(event, TurnUsage):
                    self.call_from_thread(self._show_usage, event)
                elif isinstance(event, Cancelled):
                    self.call_from_thread(self._stopped, event.text)
                elif isinstance(event, Completed):
                    self.call_from_thread(self._finish_answer, event.text)
        except Exception as exc:
            self.call_from_thread(self._show_error, exc)
        finally:
            self.call_from_thread(self._done)

    def action_stop(self) -> None:
        """Esc：关闭命令面板；否则请求终止当前输出。压缩过程不响应。"""
        if self._palette_visible:
            self._hide_palette()
            return
        if not (self._busy and self._cancellable) or self._stop_requested:
            return
        self._stop_requested = True
        if self._stop_event is not None:
            self._stop_event.set()
        self.agent.cancel()
        self._set_status("正在停止…", "#ffb86b")
        self._refresh_hint()

    def _append(self, text: str) -> None:
        """流式追加文本；工具调用之后会另起一条助手消息。"""
        if self._answer is None:
            self._set_status("回答中…", "#4d6bfe")
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
        self._set_status("执行工具…", "#4d6bfe")
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
        self._set_status("思考中…", "#4d6bfe")
        self._scroll()

    def _show_usage(self, usage: TurnUsage) -> None:
        """在每次模型调用后显示本次 Token 用量。"""
        prompt = f"输入 {usage.prompt_tokens:,}"
        if usage.cached_tokens:
            prompt += f"（缓存命中 {usage.cached_tokens:,}）"
        output = f"输出 {usage.completion_tokens:,}"
        if usage.reasoning_tokens:
            output += f"（推理 {usage.reasoning_tokens:,}）"
        text = (
            f"✦ 本次思考 · {prompt} · {output}"
            f" · 合计 {usage.total_tokens:,} tokens"
        )
        if usage.estimated:
            text += "（估算）"
        color = "#ffb86b" if usage.estimated else "#6f6f6f"
        self.query_one("#log", VerticalScroll).mount(Horizontal(
            Static(Text(text, style=color), classes="usage-pill"),
            classes="usage-row",
        ))
        self._scroll()

    def _stopped(self, text: str) -> None:
        """用户终止输出：保留已生成内容，并留下可见标记。"""
        if text.strip():
            self._finish_answer(text)
        if self._tool_pill is not None:
            self._tool_pill.update(Text(
                f"■ {self._tool_label} 已终止", style="#ffb86b",
            ))
            self._tool_pill = None
        self.query_one("#log", VerticalScroll).mount(Horizontal(
            Static(Text("■ 已停止本次输出", style="#ffb86b"), classes="stopped-pill"),
            classes="notice-row",
        ))
        self._set_status("已停止", "#ffb86b")
        self._scroll()

    def _show_error(self, exc: Exception) -> None:
        self.query_one("#log", VerticalScroll).mount(Horizontal(
            Static(Text(f"错误 · {exc}"), classes="error-pill"),
            classes="tool-row",
        ))
        self._scroll()

    def _scroll(self) -> None:
        self.query_one("#log", VerticalScroll).scroll_end(animate=False)

    def _refresh_model_label(self) -> None:
        model = getattr(self.agent, "model", "未知")
        text = model if self.size.width < 100 else f"模型 {model}"
        self.query_one("#model-label", Static).update(text)

    def _set_status(self, text: str, color: str = "#8b8b8b",
                    dot: str | None = None) -> None:
        self.query_one("#status", Static).update(
            Text.assemble(("● ", dot or color), (text, color))
        )

    def _refresh_hint(self, blocked: bool | None = None) -> None:
        if self._busy:
            if not self._cancellable:
                text = ""
            elif self._stop_requested:
                text = "停止中…"
            else:
                text = "Esc 停止生成" if self.size.width >= 100 else "Esc 停止"
        else:
            if blocked is None:
                blocked = self.agent.context_stats().blocked
            if blocked:
                text = "输入 /compact" if self.size.width >= 100 else "/compact"
            else:
                text = (
                    "Enter 发送 · / 命令 · Ctrl+C 退出"
                    if self.size.width >= 100 else "Enter 发送 · / 命令"
                )
        self.query_one("#hint", Static).update(text)

    def _notice(self, text: str, classes: str) -> None:
        self.query_one("#log", VerticalScroll).mount(Horizontal(
            Static(Text(text), classes=classes),
            classes="notice-row",
        ))
        self._scroll()

    def _update_context(self, stats: ContextStats) -> None:
        label = f"上下文 {stats.used / 1000:.1f}k/{stats.window / 1000:.0f}k"
        if stats.default_window:
            label += "（默认）"
        label += f" · 已用 {stats.percent:.1f}%"
        color = "#ff8a8a" if stats.blocked else "#8b8b8b"
        self.query_one("#context", Static).update(Text(label, style=color))

        prompt = self.query_one("#prompt", PromptInput)
        if stats.blocked:
            prompt.placeholder = "上下文已满，请输入 /compact"
            if not self._busy:
                self._set_status("待压缩", "#ff8a8a")
            if not self._context_warned:
                self._context_warned = True
                self._notice(
                    f"上下文已使用 {stats.percent:.1f}%，请输入 /compact 压缩上下文；"
                    "压缩完成前将暂停普通对话。",
                    "context-warning",
                )
        else:
            self._context_warned = False
            prompt.placeholder = "给 ZAgent 发送消息…（输入 / 查看命令）"
            if not self._busy:
                self._set_status("就绪", "#8b8b8b", "#7fbf8a")
        self._refresh_hint(stats.blocked)

    def _start_compact(self) -> None:
        self._pre_compact_stats = self.agent.context_stats()
        self._busy = True
        self._cancellable = False
        self._stop_requested = False
        self._stop_event = None
        self._set_status("压缩中…", "#ffb86b")
        self._refresh_hint()
        self._remove_welcome()

        prompt = self.query_one("#prompt", PromptInput)
        self._clear_prompt()
        self._hide_palette()
        prompt.disabled = True
        prompt.placeholder = "正在压缩上下文…"

        self._answer = None
        self._answer_row = None
        self._answer_text = ""
        self._tool_label = "压缩上下文"
        self._tool_pill = Static(Text("⚙ 正在压缩上下文…"), classes="tool-pill")
        self.query_one("#log", VerticalScroll).mount(
            Horizontal(self._tool_pill, classes="tool-row"),
        )
        self._scroll()
        self._compact_worker()

    @work(thread=True, exclusive=True)
    def _compact_worker(self) -> None:
        try:
            result = self.agent.compact()
        except Exception as exc:
            self.call_from_thread(self._compact_failed, str(exc))
            return
        if not result.ok:
            self.call_from_thread(self._compact_failed, result.error or "未知错误")
            return

        original = ""
        if not result.skipped and result.archive_path:
            try:
                original = render_transcript(read_archive(result.archive_path))
            except Exception as exc:
                original = f"读取归档失败：{exc}"
        self.call_from_thread(self._compact_done, result, original)

    def _compact_done(self, result: CompactionResult, original: str = "") -> None:
        if self._tool_pill is not None:
            label = "✓ 无需压缩" if result.skipped else "✓ 上下文压缩完成"
            self._tool_pill.update(Text(label, style="#7fbf8a"))
            self._tool_pill = None
        if result.skipped:
            self._notice("当前没有可压缩的对话历史。", "context-info")
        else:
            self._notice(
                f"上下文已压缩，摘要约 {result.summary_tokens / 1000:.1f}k tokens；"
                f"原始记录归档为 {result.archive_id}。"
                "需要历史细节时可使用 recallContext 检索。",
                "context-info",
            )
        self._update_context(self.agent.context_stats())
        self._finish_busy()

        if not result.skipped:
            before = self._pre_compact_stats.used if self._pre_compact_stats else None
            self.push_screen(CompactLogScreen(
                result.archive_id,
                original or "（归档内容为空）",
                result.summary or "（摘要内容为空）",
                result.summary_tokens,
                before,
            ))

    def _compact_failed(self, error: str) -> None:
        if self._tool_pill is not None:
            self._tool_pill.update(Text("✗ 上下文压缩失败", style="#ff8a8a"))
            self._tool_pill = None
        self._notice(
            f"压缩失败：{error}。原有上下文已保留，可重新输入 /compact 重试。",
            "context-error",
        )
        self._finish_busy()

    def _finish_busy(self) -> None:
        self._busy = False
        self._cancellable = False
        self._stop_requested = False
        self._stop_event = None
        prompt = self.query_one("#prompt", PromptInput)
        stats = self.agent.context_stats()
        if stats.blocked:
            prompt.placeholder = "上下文已满，请输入 /compact"
            self._set_status("待压缩", "#ff8a8a")
        else:
            prompt.placeholder = "给 ZAgent 发送消息…（输入 / 查看命令）"
            self._set_status("就绪", "#8b8b8b", "#7fbf8a")
        self._refresh_hint(stats.blocked)
        self._refresh_sidebar()
        prompt.disabled = False
        prompt.focus()
        self._scroll()

    def _done(self) -> None:
        self._finish_busy()
