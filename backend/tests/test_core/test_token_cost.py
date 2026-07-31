"""token/cost.py 成本计算器测试"""

import pytest

from src.token.cost import CostCalculator, cost_calculator


class TestCostCalculator:
    @pytest.fixture
    def calc(self) -> CostCalculator:
        return CostCalculator()

    def test_known_model_qwen_plus(self, calc: CostCalculator) -> None:
        cost = calc.calculate("dashscope", "qwen-plus", 1000, 500)
        # 1000/1000*0.0008 + 500/1000*0.002 = 0.0008 + 0.001 = 0.0018
        assert cost == 0.0018

    def test_known_model_gpt4o(self, calc: CostCalculator) -> None:
        cost = calc.calculate("openai", "gpt-4o", 1000, 1000)
        # 1000/1000*0.018 + 1000/1000*0.072 = 0.018 + 0.072 = 0.09
        assert cost == 0.09

    def test_embedding_model_no_output_cost(self, calc: CostCalculator) -> None:
        cost = calc.calculate("dashscope", "text-embedding-v3", 1000, 0)
        assert cost == 0.0007

    def test_ollama_cheap(self, calc: CostCalculator) -> None:
        cost = calc.calculate("ollama", "deepseek-r1:8b", 10000, 5000)
        # 10000/1000*0.00001 + 5000/1000*0.00001 = 0.0001 + 0.00005 = 0.00015
        assert cost == 0.00015

    def test_unknown_model_uses_default(self, calc: CostCalculator) -> None:
        cost = calc.calculate("some_provider", "some_model", 1000, 500)
        # 默认: 1000/1000*0.0008 + 500/1000*0.002 = 0.0018
        assert cost == 0.0018

    def test_cache_read_discount(self, calc: CostCalculator, monkeypatch) -> None:
        monkeypatch.setattr("src.token.cost.settings.TOKEN_CACHE_READ_DISCOUNT", 0.1)
        # cache_read: 500*0.1*0.0008/1000 = 0.00004
        # remaining: 500/1000*0.0008 = 0.0004
        # output: 500/1000*0.002 = 0.001
        # total = 0.00144
        cost = calc.calculate("dashscope", "qwen-plus", 1000, 500, cache_read_tokens=500)
        expected = (500 / 1000) * 0.0008 * 0.1 + (500 / 1000) * 0.0008 + (500 / 1000) * 0.002
        assert cost == round(expected, 6)

    def test_cache_write_premium(self, calc: CostCalculator, monkeypatch) -> None:
        monkeypatch.setattr("src.token.cost.settings.TOKEN_CACHE_WRITE_PREMIUM", 1.25)
        # cache_creation: 300*1.25*0.0008/1000 = 0.0003
        # remaining: 700/1000*0.0008 = 0.00056
        # output: 500/1000*0.002 = 0.001
        # total = 0.00186
        cost = calc.calculate("dashscope", "qwen-plus", 1000, 500, cache_creation_tokens=300)
        expected = (300 / 1000) * 0.0008 * 1.25 + (700 / 1000) * 0.0008 + (500 / 1000) * 0.002
        assert cost == round(expected, 6)

    def test_zero_tokens(self, calc: CostCalculator) -> None:
        cost = calc.calculate("dashscope", "qwen-plus", 0, 0)
        assert cost == 0.0

    def test_get_input_price(self, calc: CostCalculator) -> None:
        assert calc.get_input_price("dashscope", "qwen-plus") == 0.0008
        assert calc.get_input_price("unknown", "model") == 0.0008  # default

    def test_get_output_price(self, calc: CostCalculator) -> None:
        assert calc.get_output_price("openai", "gpt-4o") == 0.072

    def test_global_instance(self) -> None:
        assert isinstance(cost_calculator, CostCalculator)

    def test_anthropic_claude(self, calc: CostCalculator) -> None:
        cost = calc.calculate("anthropic", "claude-3.5-sonnet", 1000, 1000)
        assert cost == round(1000 / 1000 * 0.0216 + 1000 / 1000 * 0.108, 6)

    def test_mixed_cache_both(self, calc: CostCalculator, monkeypatch) -> None:
        """同时有 cache_read 和 cache_creation"""
        monkeypatch.setattr("src.token.cost.settings.TOKEN_CACHE_READ_DISCOUNT", 0.1)
        monkeypatch.setattr("src.token.cost.settings.TOKEN_CACHE_WRITE_PREMIUM", 1.25)
        # cache_read=400(discount), cache_creation=300(premium), remaining=300(normal)
        cost = calc.calculate("dashscope", "qwen-plus", 1000, 500, cache_read_tokens=400, cache_creation_tokens=300)
        assert cost > 0
