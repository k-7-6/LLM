from typing import Iterator

from .config import Config
from .events import Completed, Event, Token, ToolFinished, ToolStarted
from .llm import LLMClient
from .skills import Skill, system_prompt
from .tools import execute, schemas


class Agent:
    """对话编排：消息历史、流式输出、工具调用。与界面完全解耦。"""

    def __init__(self, config: Config, llm: LLMClient | None = None,
                 skills: list[Skill] | None = None):
        self._llm = llm or LLMClient(config)
        self.skills: list[Skill] = list(skills or [])
        self.messages: list[dict] = []
        prompt = system_prompt(self.skills)
        if prompt:
            self.messages.append({"role": "system", "content": prompt})

    def ask(self, prompt: str) -> Iterator[Event]:
        self.messages.append({"role": "user", "content": prompt})

        while True:
            reply = ""
            calls = {}
            stream = self._llm.stream_chat(self.messages, schemas())

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    reply += delta.content
                    yield Token(delta.content)
                for tc in delta.tool_calls or []:
                    call = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        call["id"] = tc.id
                    if tc.function.name:
                        call["name"] += tc.function.name
                    if tc.function.arguments:
                        call["arguments"] += tc.function.arguments

            if not calls:
                self.messages.append({"role": "assistant", "content": reply})
                yield Completed(reply)
                return

            self.messages.append({
                "role": "assistant",
                "content": reply or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in calls.values()
                ],
            })
            for call in calls.values():
                yield ToolStarted(call["name"], call["arguments"])
                result = execute(call["name"], call["arguments"])
                yield ToolFinished(call["name"], result)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                })
