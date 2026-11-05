"""首次运行提示：config.ini 已自动生成，修改后重新启动。"""

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfigNoticeScreen(ModalScreen):
    """提示用户填写 config.ini；关闭后由 App 退出。"""

    BINDINGS = [("escape", "close", "退出")]

    DEFAULT_CSS = """
    ConfigNoticeScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.78);
    }
    #config-dialog {
        width: 82%;
        height: auto;
        max-width: 96;
        background: #1b1b1b;
        border: round #e0a84b;
        padding: 1 2;
    }
    #config-title {
        width: 1fr;
        text-align: center;
        text-style: bold;
        color: #ffcc7a;
    }
    #config-path {
        width: 1fr;
        margin-top: 1;
        padding: 0 1;
        background: #151515;
        color: #9fd0ff;
    }
    #config-body {
        width: 1fr;
        height: auto;
        margin-top: 1;
        color: #d6d6d6;
    }
    #config-actions {
        width: 1fr;
        height: 3;
        align: right middle;
        margin-top: 1;
    }
    #config-exit {
        width: auto;
        min-width: 0;
        background: #2a2a2a;
        color: #f0f0f0;
        border: round #4d6bfe;
    }
    #config-exit:hover {
        background: #333333;
        border: round #6a86ff;
    }
    """

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def compose(self) -> ComposeResult:
        with Vertical(id="config-dialog"):
            yield Static(
                Text("⚙ 首次运行：已生成配置文件"),
                id="config-title",
            )
            yield Static(self.path, id="config-path")
            yield Static(
                Text(
                    "请编辑该文件，至少填写 [llm] 中的 api_key、base_url "
                    "和 model，并按需填写 [search] 的 API Key。\n\n"
                    "保存文件后请重新启动 ZAgent，新的配置才会生效。"
                ),
                id="config-body",
            )
            with Horizontal(id="config-actions"):
                yield Button("退出 ZAgent", id="config-exit")

    def on_mount(self) -> None:
        self.query_one("#config-exit", Button).focus()

    @on(Button.Pressed, "#config-exit")
    def _exit_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
