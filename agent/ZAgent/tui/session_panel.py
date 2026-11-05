"""历史会话面板：上下键选择，回车恢复，Esc 取消。"""

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option

from core.sessions import SessionInfo


class ResumeScreen(ModalScreen):
    """浮动会话列表，关闭时返回选中的会话 id 或 None。"""

    BINDINGS = [("escape", "cancel", "取消")]

    DEFAULT_CSS = """
    ResumeScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.72);
    }
    #resume-dialog {
        width: 78%;
        height: 72%;
        max-width: 110;
        background: #1b1b1b;
        border: round #4d6bfe;
        padding: 0 1;
    }
    #resume-head {
        height: 3;
        align: left middle;
    }
    #resume-heading {
        width: 1fr;
        content-align: left middle;
        text-style: bold;
        color: #f2f2f2;
    }
    #resume-close {
        width: auto;
        min-width: 0;
        height: 3;
        background: #2a2a2a;
        color: #d6d6d6;
        border: round #3a3a3a;
    }
    #resume-close:hover {
        background: #333333;
        color: #f2f2f2;
        border: round #4d6bfe;
    }
    #resume-list {
        height: 1fr;
        background: #171717;
        border: round #2e2e2e;
    }
    #resume-list > .option-list--option {
        padding: 0 1;
    }
    #resume-list > .option-list--option-highlighted {
        background: #2b3a6b;
        color: #f2f2f2;
    }
    #resume-empty {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        color: #8b8b8b;
    }
    #resume-hint {
        height: 2;
        content-align: left middle;
        color: #6f6f6f;
        padding: 0 1;
    }
    """

    def __init__(self, sessions: list[SessionInfo]):
        super().__init__()
        self.sessions = list(sessions)

    def compose(self) -> ComposeResult:
        with Vertical(id="resume-dialog"):
            with Horizontal(id="resume-head"):
                yield Static(
                    Text.assemble(
                        ("◈ ", "#4d6bfe"), ("恢复历史会话", "bold #f2f2f2"),
                    ),
                    id="resume-heading",
                )
                yield Button("✕ 关闭", id="resume-close")
            if self.sessions:
                yield OptionList(
                    *[
                        _option(index, info)
                        for index, info in enumerate(self.sessions)
                    ],
                    id="resume-list",
                )
            else:
                yield Static("还没有已保存的会话", id="resume-empty")
            yield Static(
                "↑↓ 选择 · Enter 恢复 · Esc 取消",
                id="resume-hint",
            )

    def on_mount(self) -> None:
        try:
            self.query_one("#resume-list", OptionList).focus()
        except Exception:
            self.query_one("#resume-close", Button).focus()

    @on(OptionList.OptionSelected)
    def _option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        try:
            info = self.sessions[event.option_index]
        except (IndexError, AttributeError):
            self.dismiss(None)
            return
        self.dismiss(info.id)

    @on(Button.Pressed, "#resume-close")
    def _close_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


def _option(index: int, info: SessionInfo):
    title = info.title
    if len(title) > 34:
        title = title[:33] + "…"
    marker = " · AGENTS" if info.has_agents_md else ""
    label = (
        f"{info.updated_at}  {title}\n"
        f"        {info.id} · {info.messages} 条消息{marker}"
    )
    return Option(label, id=f"session-{index}")
