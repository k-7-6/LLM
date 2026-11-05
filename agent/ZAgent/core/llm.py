from openai import OpenAI

from .config import Config


class LLMClient:
    """对 OpenAI SDK 的薄封装，隔离传输层细节。"""

    def __init__(self, config: Config):
        self.model = config.model
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.request_timeout,
            max_retries=config.max_retries,
        )

    def stream_chat(self, messages: list[dict], tools: list[dict]):
        kwargs = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": True,
        }
        try:
            # 请求流式响应最后附带 usage，优先用真实 Token 数监控上下文。
            return self._client.chat.completions.create(
                **kwargs,
                stream_options={"include_usage": True},
            )
        except Exception as exc:
            # 部分 OpenAI 兼容服务不支持 stream_options，退回纯流式输出。
            if "stream_options" not in str(exc):
                raise
            return self._client.chat.completions.create(**kwargs)

    def complete(self, messages: list[dict], max_tokens: int | None = None):
        """非流式补全，用于生成上下文摘要。返回 (文本, usage)。"""
        kwargs = {"model": self.model, "messages": messages}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        response = self._client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""
        return text, getattr(response, "usage", None)
