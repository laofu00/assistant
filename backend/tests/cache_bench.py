"""缓存命中率模拟测试 + 成本节省分析

通过模拟典型对话场景中的工具调用，统计 ToolCache 命中率，
结合 CostCalculator 计算缓存带来的 Token 浪费减少和成本节省。

用法：
    cd backend && .venv/Scripts/python tests/cache_bench.py

前置条件：不需要服务运行（纯内存模拟）
"""

import hashlib
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.cache import ToolCache
from src.token.cost import cost_calculator

# ==================== 增强版 ToolCache（带统计） ====================


class InstrumentedCache:
    """包装 ToolCache，增加 hit/miss/total 统计"""

    def __init__(self, base_cache: ToolCache = None):
        self._cache = base_cache or ToolCache()
        self.hits: int = 0
        self.misses: int = 0
        self.fallback_hits: int = 0  # 过期降级命中
        self.total_requests: int = 0

    def get(self, key: str) -> str | None:
        self.total_requests += 1
        val = self._cache.get(key)
        if val is not None:
            self.hits += 1
        else:
            self.misses += 1
        return val

    def get_fallback(self, key: str) -> str | None:
        val = self._cache.get_fallback(key)
        if val is not None:
            self.fallback_hits += 1
        return val

    def put(self, key: str, value: str, ttl_ms: int | None = None):
        self._cache.put(key, value, ttl_ms)

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests

    def stats(self) -> dict:
        return {
            "total": self.total_requests,
            "hits": self.hits,
            "misses": self.misses,
            "fallback_hits": self.fallback_hits,
            "hit_rate": self.hit_rate,
            "cache_size": len(self._cache),
        }


# ==================== 模拟场景配置 ====================

# 模拟 100 轮对话，每轮可能触发 1-3 个工具调用
TOTAL_ROUNDS = 100
MAX_TOOLS_PER_ROUND = 3
CACHE_TTL_MS = 2 * 60 * 1000  # 2 分钟，与 ToolCache.DEFAULT_TTL_MS 一致

# 模拟的工具列表（名称、平均输入 token、平均输出 token）
TOOLS = [
    {"name": "search_knowledge", "input_tokens": 350, "output_tokens": 800, "repeat_rate": 0.4},
    {"name": "get_current_time", "input_tokens": 50, "output_tokens": 80, "repeat_rate": 0.6},
    {"name": "get_weather", "input_tokens": 80, "output_tokens": 200, "repeat_rate": 0.5},
    {"name": "list_memos", "input_tokens": 100, "output_tokens": 500, "repeat_rate": 0.3},
    {"name": "send_email", "input_tokens": 200, "output_tokens": 150, "repeat_rate": 0.05},
    {"name": "add_memo", "input_tokens": 120, "output_tokens": 100, "repeat_rate": 0.1},
    {"name": "get_user_info", "input_tokens": 60, "output_tokens": 300, "repeat_rate": 0.35},
]


def _make_query(tool_name: str) -> tuple[str, str]:
    """生成模拟查询，repeat_prob 概率重复历史查询"""
    params = hashlib.md5(str(random.random()).encode()).hexdigest()[:8]
    return f"{tool_name}:user_001:{params}", params


def run_simulation():
    print("=" * 60)
    print("  工具缓存命中率与成本节省模拟")
    print("=" * 60)
    print(f"  模拟轮次:   {TOTAL_ROUNDS}")
    print(f"  缓存 TTL:   {CACHE_TTL_MS/1000:.0f}s")
    print(f"  工具数量:   {len(TOOLS)}")
    print()

    cache = InstrumentedCache()
    history: dict[str, list[str]] = {}  # tool_name → 最近 query key 列表

    # 累计 token 统计
    total_input_no_cache = 0
    total_output_no_cache = 0
    total_input_with_cache = 0
    total_output_with_cache = 0
    cache_read_tokens = 0
    cache_write_tokens = 0

    # 模拟对话轮次
    for round_id in range(1, TOTAL_ROUNDS + 1):
        tools_this_round = random.randint(1, MAX_TOOLS_PER_ROUND)
        chosen = random.choices(TOOLS, k=tools_this_round)

        for tool in chosen:
            t = tool

            # 无缓存：直接调用 LLM
            total_input_no_cache += t["input_tokens"]
            total_output_no_cache += t["output_tokens"]

            # 有缓存：先查缓存
            # 一定概率重复历史查询
            repeat = t["repeat_rate"] > random.random()
            if repeat and history.get(t["name"]):
                # 复用历史查询 key
                cache_key = random.choice(history[t["name"]])
            else:
                cache_key, _ = _make_query(t["name"])
                history.setdefault(t["name"], []).append(cache_key)
                if len(history[t["name"]]) > 20:
                    history[t["name"]] = history[t["name"]][-20:]

            # 查缓存
            cached = cache.get(cache_key)
            if cached is not None:
                # 缓存命中：读操作 0 token，写操作 0
                # 实际只需少量缓存读数（计入 cache_read）
                cache_read_tokens += t["input_tokens"]
                total_output_with_cache += t["output_tokens"]  # 输出仍需要
            else:
                # 缓存未命中：正常 LLM 调用 + 写入缓存
                total_input_with_cache += t["input_tokens"]
                total_output_with_cache += t["output_tokens"]
                # 写入缓存（缓存写入有溢价）
                cache_write_tokens += t["input_tokens"]
                # 存缓存
                result = f"mock_result_{cache_key}"
                cache.put(cache_key, result)

    # 计算成本 — 直接按 Token 算，不用 CostCalculator 的 API 层缓存模型
    model_price = cost_calculator._prices.get("dashscope-qwen-plus")
    if model_price is None:
        model_price = type("Price", (), {"input_price": 0.0008, "output_price": 0.002})

    # 无缓存：所有工具调用都走 LLM
    cost_no_cache = (total_input_no_cache / 1000) * model_price.input_price + \
                    (total_output_no_cache / 1000) * model_price.output_price

    # 有缓存：命中时跳过工具调用，节省该工具的全部 input + output Token
    hits_count = cache.hits
    avg_input_per_hit = cache_read_tokens / max(hits_count, 1)
    avg_output_per_hit = avg_input_per_hit * (total_output_no_cache / total_input_no_cache) if total_input_no_cache > 0 else 0
    saved_output = int(hits_count * avg_output_per_hit)

    cost_with_cache = cost_no_cache \
        - (cache_read_tokens / 1000) * model_price.input_price \
        - (saved_output / 1000) * model_price.output_price

    savings = cost_no_cache - cost_with_cache
    savings_pct = (savings / cost_no_cache * 100) if cost_no_cache > 0 else 0

    # 输出报告
    stats = cache.stats()
    print("─" * 60)
    print("[缓存命中率统计]")
    print("─" * 60)
    print(f"  总请求数:     {stats['total']}")
    print(f"  缓存命中:     {stats['hits']}")
    print(f"  缓存未命中:   {stats['misses']}")
    print(f"  命中率:       {stats['hit_rate']:.1%}")
    print(f"  缓存条目数:   {stats['cache_size']}")
    print()

    print("─" * 60)
    print("[Token 消耗对比]")
    print("─" * 60)
    print(f"                           无缓存          有缓存")
    print(f"  输入 Token:              {total_input_no_cache:>8,}     {total_input_with_cache:>8,}")
    print(f"  输出 Token:              {total_output_no_cache:>8,}     {total_output_with_cache:>8,}")
    print(f"  缓存写入 Token:          {'-':>8}     {cache_write_tokens:>8,}")
    print(f"  缓存命中 Token:          {'-':>8}     {cache_read_tokens:>8,}")
    print()

    print("─" * 60)
    print("[成本对比（qwen-plus 计费）]")
    print("─" * 60)
    print(f"  无缓存总成本:     ¥{cost_no_cache:>10.6f}")
    print(f"  有缓存总成本:     ¥{cost_with_cache:>10.6f}")
    print(f"  节省金额:         ¥{savings:>10.6f}")
    print(f"  节省比例:         {savings_pct:>9.1f}%")
    print()

    # 分工具命中率
    print("─" * 60)
    print("[分工具缓存效果预估]")
    print("─" * 60)
    print(f"  {'工具名':<20s}  {'重复率':>6s}  {'预估命中率':>10s}  {'输入Token':>10s}")
    print(f"  {'─'*20}  {'─'*6}  {'─'*10}  {'─'*10}")
    for t in TOOLS:
        est_hit_rate = t["repeat_rate"] * stats["hit_rate"]  # 近似估算
        saved_tokens = int(t["input_tokens"] * t["repeat_rate"] * stats["hit_rate"] * TOTAL_ROUNDS * 1.5)
        print(f"  {t['name']:<20s}  {t['repeat_rate']:>5.0%}  {est_hit_rate:>9.1%}  {saved_tokens:>10,d}")

    print()
    print("─" * 60)
    print("[简历话术建议]")
    print("─" * 60)
    print(f'  "引入工具调用结果缓存（TTL 2 分钟），在模拟 {TOTAL_ROUNDS} 轮对话中')
    print(f'   缓存命中率达 {stats["hit_rate"]:.0%}，Token 消耗减少 {total_input_no_cache - total_input_with_cache:,}')
    print(f'   （{savings_pct:.0f}%），预估成本节省 ¥{savings:.4f}。"')


if __name__ == "__main__":
    random.seed(42)  # 固定种子保证可复现
    run_simulation()
