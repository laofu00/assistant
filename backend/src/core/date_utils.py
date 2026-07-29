"""日期工具函数 — 相对日期替换、日期解析"""

import re
from datetime import date, datetime, timedelta

DATE_FORMAT = "%Y-%m-%d"


def normalize_date_terms(text: str) -> str:
    """替换文本中的相对日期为具体日期"""
    if not text:
        return text
    today = date.today()
    replacements = {
        "今天": today.strftime(DATE_FORMAT),
        "昨天": (today - timedelta(days=1)).strftime(DATE_FORMAT),
        "明天": (today + timedelta(days=1)).strftime(DATE_FORMAT),
        "后天": (today + timedelta(days=2)).strftime(DATE_FORMAT),
        "前天": (today - timedelta(days=2)).strftime(DATE_FORMAT),
    }
    result = text
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result


def parse_date(date_str: str | None) -> date | None:
    """解析日期字符串"""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), DATE_FORMAT).date()
    except ValueError:
        pass
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str.strip())
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None
