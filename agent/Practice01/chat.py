import configparser
import os
import sys
import traceback

from openai import OpenAI

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 按脚本自身位置找 config.ini，双击运行也能找到
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

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

        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        reply = ""
        for chunk in stream:
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content
            if piece:
                reply += piece
                print(piece, end="", flush=True)
                # 想看模型的思考过程就再加这两行:
                # if chunk.choices[0].delta.reasoning_content:
                #     print(chunk.choices[0].delta.reasoning_content, end="", flush=True)
        print()

        messages.append({"role": "assistant", "content": reply})
        print()
except Exception:
    traceback.print_exc()
    try:
        input("\n出错了，按回车键关闭窗口...")
    except EOFError:
        pass
