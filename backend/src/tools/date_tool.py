"""日期工具 — @tool 封装（4 个方法）

对齐 Java 版 DateTool：getCurrentDate/getDateAfterDays/getCurrentDateTime/parseDateRange
"""

import json
import re
from datetime import date, datetime, timedelta

from langchain_core.tools import tool

_CHINESE_DAYS = ["", "一", "二", "三", "四", "五", "六", "日"]
_DAY_NAME_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}


def _weekday_chinese(d: date) -> str:
    return _CHINESE_DAYS[d.isoweekday()]


@tool
def get_current_date() -> str:
    """获取当前日期信息：今天日期、星期、本周起止、本月起止、明天、昨天"""
    today = date.today()
    # 本周起止
    weekday = today.isoweekday()
    monday = today - timedelta(days=weekday - 1)
    sunday = monday + timedelta(days=6)
    # 本月起止
    first_day = today.replace(day=1)
    if today.month == 12:
        last_day = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last_day = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    now = datetime.now()
    return (
        f"当前日期信息：\n"
        f"- 当前日期：{today}\n"
        f"- 星期：{_weekday_chinese(today)}\n"
        f"- 当前时间：{now:%H:%M:%S}\n"
        f"- 明天：{today + timedelta(days=1)}\n"
        f"- 昨天：{today - timedelta(days=1)}\n"
        f"- 本周起始（周一）：{monday}\n"
        f"- 本周结束（周日）：{sunday}\n"
        f"- 本月起始：{first_day}\n"
        f"- 本月结束：{last_day}"
    )


@tool
def get_date_after_days(days: int) -> str:
    """计算N天后的日期。

    Args:
        days: 天数（正数未来，负数过去）
    """
    d = date.today() + timedelta(days=days)
    return f"{d}，星期{_weekday_chinese(d)}"


@tool
def get_current_datetime() -> str:
    """获取当前完整日期时间（精确到秒）"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
def parse_date_range(description: str) -> str:
    """将自然语言日期描述解析为标准日期范围（startDate/endDate）。

    支持：今天/昨天/明天/本周/下周/上周/本月/下月/上月/下周一/本周三/上周日/2026年7月2日/2026-07-02

    Args:
        description: 自然语言日期描述
    """
    if not description or not description.strip():
        return json.dumps({"error": "日期描述不能为空"}, ensure_ascii=False)

    desc = description.strip()
    today = date.today()
    weekday = today.isoweekday()  # 1=Mon, 7=Sun

    # 标准映射
    mapping: dict[str, tuple[date, date]] = {
        "今天": (today, today),
        "昨天": (today - timedelta(days=1), today - timedelta(days=1)),
        "明天": (today + timedelta(days=1), today + timedelta(days=1)),
        "本周": (today - timedelta(days=weekday - 1), today - timedelta(days=weekday - 1) + timedelta(days=6)),
        "下周": (today - timedelta(days=weekday - 1) + timedelta(days=7), today - timedelta(days=weekday - 1) + timedelta(days=13)),
        "上周": (today - timedelta(days=weekday - 1) - timedelta(days=7), today - timedelta(days=weekday - 1) - timedelta(days=1)),
        "本月": (today.replace(day=1), _month_end(today)),
        "下月": (_next_month_start(today), _next_month_end(today)),
        "上月": (_prev_month_start(today), _prev_month_end(today)),
    }

    if desc in mapping:
        start, end = mapping[desc]
        return json.dumps({"startDate": str(start), "endDate": str(end)}, ensure_ascii=False)

    # 组合日期：下周一、本周三
    combined = _parse_combined_date(desc)
    if combined:
        return json.dumps({"startDate": str(combined), "endDate": str(combined)}, ensure_ascii=False)

    # 具体日期格式
    concrete = _parse_concrete_date(desc)
    if concrete:
        return json.dumps({"startDate": str(concrete), "endDate": str(concrete)}, ensure_ascii=False)

    return json.dumps({"error": f"无法识别的日期描述: {desc}，支持：今天、本周、下周一、2026-07-02等"}, ensure_ascii=False)


def _month_end(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1, day=1) - timedelta(days=1)
    return d.replace(month=d.month + 1, day=1) - timedelta(days=1)


def _next_month_start(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1, day=1)
    return d.replace(month=d.month + 1, day=1)


def _next_month_end(d: date) -> date:
    start = _next_month_start(d)
    return _month_end(start)


def _prev_month_start(d: date) -> date:
    if d.month == 1:
        return d.replace(year=d.year - 1, month=12, day=1)
    return d.replace(month=d.month - 1, day=1)


def _prev_month_end(d: date) -> date:
    if d.month == 1:
        return d.replace(year=d.year - 1, month=12, day=1)
    return d.replace(month=d.month, day=1) - timedelta(days=1)


def _parse_combined_date(desc: str) -> date | None:
    """解析组合日期：本周一~本周日、下周一~下周日"""
    m = re.match(r"(本周|下周|上周)(周(一|二|三|四|五|六|日)|星期(一|二|三|四|五|六|日|天))", desc)
    if not m:
        return None
    week_ref = m.group(1)
    day_str = m.group(2)
    target_day_num = None
    for name, num in _DAY_NAME_MAP.items():
        if name in day_str:
            target_day_num = num
            break
    if target_day_num is None:
        return None

    today = date.today()
    this_monday = today - timedelta(days=today.isoweekday() - 1)

    base_monday = {
        "本周": this_monday,
        "下周": this_monday + timedelta(days=7),
        "上周": this_monday - timedelta(days=7),
    }.get(week_ref)

    if base_monday is None:
        return None

    return base_monday + timedelta(days=target_day_num - 1)


def _parse_concrete_date(desc: str) -> date | None:
    """解析具体日期：2026年7月2日 或 2026-07-02"""
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", desc)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", desc)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None
