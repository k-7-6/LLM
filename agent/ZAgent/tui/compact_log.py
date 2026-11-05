"""压缩日志面板：左右对照压缩前的原文与压缩后的摘要。"""

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea


class CompactLogScreen(ModalScreen):
    """浮动日志：两栏各自滚动，可点击关闭按钮或按 Esc 关闭。"""

    BINDINGS = [("escape", "close", "关闭")]

    DEFAULT_CSS = """
    CompactLogScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.72);
    }
    #compact-dialog {
        width: 94%;
        height: 90%;
        max-width: 160;
        background: #1b1b1b;
        border: round #4d6bfe;
        padding: 0 1;
    }
    #compact-head {
        height: 3;
        align: left middle;
    }
    #compact-heading {
        width: 1fr;
        content-align: left middle;
        text-style: bold;
        color: #f2f2f2;
    }
    #compact-meta {
        width: auto;
        content-align: right middle;
        color: #8b8b8b;
        margin-right: 1;
    }
    #compact-close {
        width: auto;
        min-width: 0;
        height: 3;
        background: #2a2a2a;
        color: #d6d6d6;
        border: round #3a3a3a;
    }
    #compact-close:hover {
        background: #333333;
        color: #f2f2f2;
        border: round #4d6bfe;
    }
    #compact-columns {
        height: 1fr;
    }
    .compact-column {
        width: 1fr;
        height: 1fr;
        margin: 0 1;
        background: #171717;
        border: round #2e2e2e;
    }
    .compact-title {
        width: 1fr;
        height: 2;
        content-align: left middle;
        padding: 0 1;
        background: #202020;
        color: #9a9a9a;
        text-style: bold;
    }
    .compact-view {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }
    """

    def __init__(self, archive_id: str, original: str, summary: str,
                 summary_tokens: int = 0, before_tokens: int | None = None):
        super().__init__()
        self.archive_id = archive_id
        self.original = original
        self.summary = summary
        self.summary_tokens = summary_tokens
        self.before_tokens = before_tokens

    def compose(self) -> ComposeResult:
        meta = f"归档 {self.archive_id}" if self.archive_id else "未归档"
        if self.before_tokens:
            meta += f" · 压缩前 {_tokens(self.before_tokens)} tokens"
        if self.summary_tokens:
            meta += f" → 摘要 {_tokens(self.summary_tokens)} tokens"

        left_title = f"压缩前原文 · {len(self.original):,} 字符"
        right_title = f"压缩后摘要 · {len(self.summary):,} 字符"

        with Vertical(id="compact-dialog"):
            with Horizontal(id="compact-head"):
                yield Static(
                    Text.assemble(("◈ ", "#4d6bfe"), ("上下文压缩日志", "bold #f2f2f2")),
                    id="compact-heading",
                )
                yield Static(meta, id="compact-meta")
                yield Button("✕ 关闭", id="compact-close")
            with Horizontal(id="compact-columns"):
                with Vertical(classes="compact-column"):
                    yield Static(left_title, classes="compact-title")
                    yield TextArea(
                        self.original,
                        read_only=True,
                        soft_wrap=True,
                        show_line_numbers=False,
                        highlight_cursor_line=False,
                        id="compact-original",
                        classes="compact-view",
                    )
                with Vertical(classes="compact-column"):
                    yield Static(right_title, classes="compact-title")
                    yield TextArea(
                        self.summary,
                        read_only=True,
                        soft_wrap=True,
                        show_line_numbers=False,
                        highlight_cursor_line=False,
                        id="compact-summary",
                        classes="compact-view",
                    )

    def on_mount(self) -> None:
        self.query_one("#compact-original", TextArea).focus()

    @on(Button.Pressed, "#compact-close")
    def _close_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


def _tokens(value: int) -> str:
    return f"{value / 1000:.1f}k" if value >= 1000 else str(value)
