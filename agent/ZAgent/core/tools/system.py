import subprocess

from .registry import Tool, register


def _getdate(_args: dict) -> str:
    out = subprocess.run(
        "date /T && time /T",
        shell=True, capture_output=True, text=True, errors="replace",
    )
    return out.stdout.strip() or out.stderr.strip()


def _isleapyear(args: dict) -> str:
    year = args["year"]
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return f"{year} 是闰年" if leap else f"{year} 不是闰年"


register(Tool(
    name="getdate",
    description="获取当前电脑的日期和时间",
    parameters={"type": "object", "properties": {}},
    handler=_getdate,
))

register(Tool(
    name="isleapyear",
    description="判断指定年份是否为闰年",
    parameters={
        "type": "object",
        "properties": {"year": {"type": "integer", "description": "要判断的年份，例如 2024"}},
        "required": ["year"],
    },
    handler=_isleapyear,
))
