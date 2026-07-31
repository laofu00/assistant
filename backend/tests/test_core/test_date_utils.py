"""core/date_utils.py 日期工具测试"""

from datetime import date

import pytest

from src.core.date_utils import normalize_date_terms, parse_date


class TestNormalizeDateTerms:
    def test_today(self) -> None:
        result = normalize_date_terms("今天")
        today = date.today().strftime("%Y-%m-%d")
        assert result == today

    def test_yesterday(self) -> None:
        from datetime import timedelta
        result = normalize_date_terms("昨天")
        expected = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert result == expected

    def test_tomorrow(self) -> None:
        from datetime import timedelta
        result = normalize_date_terms("明天")
        expected = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        assert result == expected

    def test_multiple_terms(self) -> None:
        result = normalize_date_terms("今天和明天的安排")
        assert date.today().strftime("%Y-%m-%d") in result

    def test_empty_string(self) -> None:
        assert normalize_date_terms("") == ""

    def test_no_date_terms(self) -> None:
        assert normalize_date_terms("查询备忘录") == "查询备忘录"


class TestParseDate:
    def test_standard_format(self) -> None:
        result = parse_date("2025-03-15")
        assert result == date(2025, 3, 15)

    def test_chinese_format(self) -> None:
        result = parse_date("2025年3月15日")
        assert result == date(2025, 3, 15)

    def test_chinese_with_padded_month(self) -> None:
        result = parse_date("2025年12月5日")
        assert result == date(2025, 12, 5)

    def test_none_input(self) -> None:
        assert parse_date(None) is None

    def test_empty_string(self) -> None:
        assert parse_date("") is None

    def test_whitespace_only(self) -> None:
        assert parse_date("   ") is None

    def test_invalid_format(self) -> None:
        assert parse_date("not-a-date") is None

    def test_invalid_month(self) -> None:
        assert parse_date("2025-13-01") is None
