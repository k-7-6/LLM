import re

from core.tools import system


def test_getdate_returns_local_time_and_weekday():
    text = system._getdate({})
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} 星期[一二三四五六日]", text
    )


def test_isleapyear_rules():
    assert system._isleapyear({"year": 2024}) == "2024 是闰年"
    assert system._isleapyear({"year": 2000}) == "2000 是闰年"
    assert system._isleapyear({"year": 1900}) == "1900 不是闰年"
    assert system._isleapyear({"year": 2023}) == "2023 不是闰年"
