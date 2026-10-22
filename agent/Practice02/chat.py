import configparser
import os
import subprocess
import sys
import traceback

from openai import OpenAI

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

tools = [{
    "type": "function",
    "function": {
        "name": "getdate",
        "description": "获取当前电脑的日期和时间",
        "parameters": {"type": "object", "properties": {}},
    },
}]

try:
    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8")

    base_url = config["llm"]["base_url"]
    api_key = config["llm"]["api_key"]
    model = config["llm"]["model"]

    client = OpenAI(base_url=base_url, api_key=api_key)
    messages = []

    print("按 Ctrl+C 退出")
    while True:
        prompt = input("你好请提出你的问题: ")
        messages.append({"role": "user", "content": prompt})
        print("-----")

        while True:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                stream=True,
            )
            reply = ""
            calls = {}
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    reply += delta.content
                    print(delta.content, end="", flush=True)
                for tc in delta.tool_calls or []:
                    c = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        c["id"] = tc.id
                    if tc.function.name:
                        c["name"] += tc.function.name
                    if tc.function.arguments:
                        c["arguments"] += tc.function.arguments

            if not calls:
                messages.append({"role": "assistant", "content": reply})
                print()
                break

            messages.append({
                "role": "assistant",
                "content": reply or None,
                "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for c in calls.values()
                ],
            })
            for c in calls.values():
                out = subprocess.run(
                    "date /T && time /T",
                    shell=True, capture_output=True, text=True, errors="replace",
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": c["id"],
                    "content": out.stdout.strip() or out.stderr.strip(),
                })
except Exception:
    traceback.print_exc()
    try:
        input("\n出错了，按回车键关闭窗口...")
    except EOFError:
        pass
