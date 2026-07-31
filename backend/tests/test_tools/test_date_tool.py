"""tools/date_tool.py 日期工具测试（4个）"""

import json
from datetime import date, timedelta
from unittest.mock import patch

from src.tools.date_tool import (
    get_current_date,
    get_current_datetime,
    get_date_after_days,
    parse_date_range,
)


class TestGetCurrentDate:
    def test_returns_string_with_info(self) -> None:
        result = get_current_date.invoke({})
        assert "当前日期" in result
        assert "星期" in result
        assert "本周" in result
        assert "本月" in result

    def test_contains_today(self) -> None:
        today = date.today()
        result = get_current_date.invoke({})
        assert str(today) in result


class TestGetDateAfterDays:
    def test_positive_days(self) -> None:
        target = date.today() + timedelta(days=7)
        result = get_date_after_days.invoke({"days": 7})
        assert str(target) in result

    def test_negative_days(self) -> None:
        target = date.today() + timedelta(days=-3)
        result = get_date_after_days.invoke({"days": -3})
        assert str(target) in result

    def test_zero_days(self) -> None:
        target = date.today()
        result = get_date_after_days.invoke({"days": 0})
        assert str(target) in result


class TestGetCurrentDatetime:
    def test_returns_iso_format(self) -> None:
        result = get_current_datetime.invoke({})
        # Format: YYYY-MM-DD HH:MM:SS
        parts = result.split(" ")
        assert len(parts) == 2
        assert len(parts[0].split("-")) == 3
        assert len(parts[1].split(":")) == 3


class TestParseDateRange:
    def test_today(self) -> None:
        today = date.today()
        result = json.loads(parse_date_range.invoke({"description": "今天"}))
        assert result["startDate"] == str(today)
        assert result["endDate"] == str(today)

    def test_this_week(self) -> None:
        result = json.loads(parse_date_range.invoke({"description": "本周"}))
        assert "startDate" in result
        assert "endDate" in result

    def test_this_month(self) -> None:
        result = json.loads(parse_date_range.invoke({"description": "本月"}))
        assert "startDate" in result
        assert "endDate" in result

    def test_concrete_date_chinese(self) -> None:
        result = json.loads(parse_date_range.invoke({"description": "2025年3月15日"}))
        assert result["startDate"] == "2025-03-15"

    def test_concrete_date_iso(self) -> None:
        result = json.loads(parse_date_range.invoke({"description": "2025-03-15"}))
        assert result["startDate"] == "2025-03-15"

    def test_empty_description(self) -> None:
        result = json.loads(parse_date_range.invoke({"description": ""}))
        assert "error" in result

    def test_unrecognized(self) -> None:
        result = json.loads(parse_date_range.invoke({"description": "下周五"}))
        assert "startDate" in result or "error" in result
