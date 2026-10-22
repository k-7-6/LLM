from openai import OpenAI

from .config import Config


class LLMClient:
    """对 OpenAI SDK 的薄封装，隔离传输层细节。"""

    def __init__(self, config: Config):
        self.model = config.model
        self._client = OpenAI(base_url=config.base_url, api_key=config.api_key)

    def stream_chat(self, messages: list[dict], tools: list[dict]):
        return self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            stream=True,
        )
