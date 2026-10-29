import os

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Input, Static

from core.agent import Agent
from core.events import Token, ToolStarted
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
}


class ChatApp(App):
    TITLE = "ZAgent 智能助手"
    SUB_TITLE = "回车发送问题 · Ctrl+C 退出"
    ENABLE_COMMAND_PALETTE = False  # 关闭内置英文命令面板（Ctrl+P）
    CSS = """
    #topbar { height: 3; align: center middle; background: $panel; }
    #title { width: 1fr; padding: 0 1; text-style: bold; }
    #features { margin-right: 1; }
    #log { height: 1fr; padding: 1 2; }
    .welcome { color: $text-muted; margin-bottom: 1; }
    .user { color: $accent; margin-top: 1; }
    .assistant { margin-bottom: 1; }
    .tool { color: $text-muted; }
    .features { border: round $primary; padding: 1; margin: 1 0; }
    """
    BINDINGS = [("ctrl+c", "quit", "退出")]

    def __init__(self, agent: Agent):
        super().__init__()
        self.agent = agent
        self._answer: Static | None = None
        self._answer_text = ""

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static(Text("ZAgent 智能助手"), id="title")
            yield Button("功能列表", id="features")
        yield VerticalScroll(id="log")
        yield Input(placeholder="输入问题，回车发送（Ctrl+C 退出）", id="prompt")
        yield Footer()

    def action_help_quit(self) -> None:
        """覆盖框架默认的 Ctrl+C 英文提示，直接退出。"""
        self.exit()

    def on_mount(self) -> None:
        log = self.query_one("#log", VerticalScroll)
        log.mount(Static(Text("你好，我是 ZAgent。可以问我问题，也可以让我查时间、判断闰年或操作文件。"), classes="welcome"))
        if self.agent.skills:
            names = "、".join(skill.name for skill in self.agent.skills)
            log.mount(Static(Text(f"已加载技能：{names}"), classes="welcome"))
        else:
            log.mount(Static(Text(
                f"未发现技能（项目根：{os.getcwd()}）。请从包含 .agents/skills 的目录启动。"
            ), classes="welcome"))
        self.query_one("#prompt", Input).focus()

    @on(Button.Pressed, "#features")
    def _show_features(self) -> None:
        lines = ["可用功能："]
        for i, tool in enumerate(catalog(), 1):
            label = TOOL_LABELS.get(tool.name, tool.name)
            lines.append(f"{i}. {label}：{tool.description}")
        if self.agent.skills:
            lines.append("")
            lines.append("可用技能：")
            for i, skill in enumerate(self.agent.skills, 1):
                lines.append(f"{i}. {skill.name}：{skill.description}")
        log = self.query_one("#log", VerticalScroll)
        log.mount(Static(Text("\n".join(lines)), classes="features"))
        log.scroll_end(animate=False)
        self.query_one("#prompt", Input).focus()

    @on(Input.Submitted)
    def _submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        prompt = self.query_one("#prompt", Input)
        prompt.value = ""
        prompt.disabled = True

        log = self.query_one("#log", VerticalScroll)
        log.mount(Static(Text(f"你：{text}"), classes="user"))
        log.scroll_end(animate=False)

        self._answer = None
        self._answer_text = ""
        self._stream(text)

    @work(thread=True, exclusive=True)
    def _stream(self, text: str) -> None:
        try:
            for event in self.agent.ask(text):
                if isinstance(event, Token):
                    self.call_from_thread(self._append, event.text)
                elif isinstance(event, ToolStarted):
                    self.call_from_thread(self._show_tool, event.name)
        except Exception as exc:
            self.call_from_thread(self._show_error, exc)
        finally:
            self.call_from_thread(self._done)

    def _append(self, text: str) -> None:
        """按到达顺序追加文本块：工具调用之后的内容会另起一块，排在工具提示下方。"""
        if self._answer is None:
            self._answer = Static("", classes="assistant")
            self._answer_text = ""
            self.query_one("#log", VerticalScroll).mount(self._answer)
        self._answer_text += text
        self._answer.update(Text(self._answer_text))
        self._scroll()

    def _show_error(self, exc: Exception) -> None:
        log = self.query_one("#log", VerticalScroll)
        log.mount(Static(Text(f"错误: {exc}", style="red")))
        log.scroll_end(animate=False)

    def _scroll(self) -> None:
        self.query_one("#log", VerticalScroll).scroll_end(animate=False)

    def _show_tool(self, name: str) -> None:
        self._answer = None
        self._answer_text = ""
        log = self.query_one("#log", VerticalScroll)
        log.mount(Static(Text(f"[工具] {TOOL_LABELS.get(name, name)}", style="dim")))
        log.scroll_end(animate=False)

    def _done(self) -> None:
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
        prompt.focus()
        self._scroll()
