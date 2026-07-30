"""成本计算服务 — 9 个模型价格配置 + 缓存折扣/溢价

对齐 Java 版 CostCalculationService
"""

from dataclasses import dataclass

from src.core.config import settings


@dataclass
class ModelPrice:
    input_price: float   # 每千 Token 输入价格（元）
    output_price: float  # 每千 Token 输出价格（元）


class CostCalculator:
    """LLM 调用成本计算器"""

    def __init__(self) -> None:
        self._prices: dict[str, ModelPrice] = {}
        self._init_prices()

    def _init_prices(self) -> None:
        """初始化 9 个模型价格配置"""
        p = self._prices

        # 通义千问
        p["dashscope-qwen-plus"] = ModelPrice(0.0008, 0.002)
        p["dashscope-qwen-max"] = ModelPrice(0.012, 0.012)
        p["dashscope-qwen-turbo"] = ModelPrice(0.0008, 0.002)

        # 嵌入模型（仅输入 token 计费，输出价格填 0）
        p["dashscope-text-embedding-v3"] = ModelPrice(0.0007, 0)
        # 重排序模型
        p["dashscope-gte-rerank"] = ModelPrice(0.0007, 0)

        # Ollama 本地模型（象征性成本）
        p["ollama-deepseek-r1:8b"] = ModelPrice(0.00001, 0.00001)
        p["ollama-llama3.2"] = ModelPrice(0.00001, 0.00001)
        p["ollama-mistral"] = ModelPrice(0.00001, 0.00001)

        # OpenAI
        p["openai-gpt-4o"] = ModelPrice(0.018, 0.072)
        p["openai-gpt-4o-mini"] = ModelPrice(0.0036, 0.0144)

        # Anthropic
        p["anthropic-claude-3.5-sonnet"] = ModelPrice(0.0216, 0.108)

    def calculate(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """计算 AI 调用成本（元）

        Args:
            provider: 模型提供商（dashscope/ollama/openai/anthropic）
            model: 模型名称
            input_tokens: 输入 Token 数
            output_tokens: 输出 Token 数
            cache_creation_tokens: 缓存写入 Token 数
            cache_read_tokens: 缓存命中 Token 数
        """
        key = f"{provider}-{model.lower()}"
        price = self._prices.get(key)

        if price is None:
            # 使用默认价格
            price = ModelPrice(settings.TOKEN_DEFAULT_INPUT_PRICE, settings.TOKEN_DEFAULT_OUTPUT_PRICE)
            self._prices[key] = price  # 缓存未知模型

        # 输入成本
        cost = 0.0
        remaining_input = input_tokens

        # 缓存命中 Token（折扣价）
        if cache_read_tokens > 0:
            cost += (cache_read_tokens / 1000) * price.input_price * settings.TOKEN_CACHE_READ_DISCOUNT
            remaining_input -= cache_read_tokens

        # 缓存写入 Token（溢价）
        if cache_creation_tokens > 0:
            cost += (cache_creation_tokens / 1000) * price.input_price * settings.TOKEN_CACHE_WRITE_PREMIUM
            remaining_input -= cache_creation_tokens

        # 剩余未缓存输入 Token
        if remaining_input > 0:
            cost += (remaining_input / 1000) * price.input_price

        # 输出成本
        if output_tokens > 0:
            cost += (output_tokens / 1000) * price.output_price

        return round(cost, 6)

    def get_input_price(self, provider: str, model: str) -> float:
        key = f"{provider}-{model.lower()}"
        return self._prices.get(key, ModelPrice(settings.TOKEN_DEFAULT_INPUT_PRICE, settings.TOKEN_DEFAULT_OUTPUT_PRICE)).input_price

    def get_output_price(self, provider: str, model: str) -> float:
        key = f"{provider}-{model.lower()}"
        return self._prices.get(key, ModelPrice(settings.TOKEN_DEFAULT_INPUT_PRICE, settings.TOKEN_DEFAULT_OUTPUT_PRICE)).output_price


# 全局实例
cost_calculator = CostCalculator()
