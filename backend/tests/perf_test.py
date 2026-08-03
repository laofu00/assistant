"""纯 asyncio + httpx 并发压测脚本（替代 Locust，避免 Windows gevent 问题）

用法：
    cd backend && .venv/Scripts/python tests/perf_test.py

输出：QPS、P50/P95/P99 延迟、TTFT
"""

import asyncio
import json
import time
from statistics import median

import httpx

BASE_URL = "http://localhost:8000"
CHAT_PATH = "/api/v1/chat/mock"
HEALTH_PATH = "/health/live"

CONCURRENT_USERS = 20
TEST_DURATION = 30  # 秒
QUERIES = [
    "什么是 RAG？",
    "LangGraph 的 Checkpointer 有什么作用？",
    "工具注册中心支持哪三种权限级别？",
    "短期记忆保留多少条对话？",
    "系统如何处理 Prompt Injection 攻击？",
]


async def get_token(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "testuser", "password": "Test123456",
    })
    return r.json()["data"]["token"]


async def health_check(client: httpx.AsyncClient, results: list):
    start = time.monotonic()
    try:
        r = await client.get(f"{BASE_URL}{HEALTH_PATH}")
        elapsed = (time.monotonic() - start) * 1000
        results.append({"type": "health", "status": r.status_code, "latency_ms": elapsed})
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        results.append({"type": "health", "status": 0, "latency_ms": elapsed, "error": str(e)})


async def chat_mock(client: httpx.AsyncClient, token: str, results: list):
    start = time.monotonic()
    ttft = None
    try:
        async with client.stream(
            "POST", f"{BASE_URL}{CHAT_PATH}",
            json={"message": __import__("random").choice(QUERIES), "user_id": "testuser"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        ) as resp:
            status = resp.status_code
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data: ") and "[DONE]" in line:
                    break
                if line.startswith("event: message") or line.startswith("data: "):
                    if ttft is None:
                        ttft = time.monotonic()

        total_time = (time.monotonic() - start) * 1000
        ttft_ms = (ttft - start) * 1000 if ttft else total_time
        results.append({
            "type": "chat", "status": status,
            "latency_ms": total_time, "ttft_ms": ttft_ms,
        })
    except Exception as e:
        total_time = (time.monotonic() - start) * 1000
        results.append({"type": "chat", "status": 0, "latency_ms": total_time, "error": str(e)})


async def user_worker(client: httpx.AsyncClient, token: str, results: list, stop_event: asyncio.Event):
    """单用户循环：发请求、等待、再发"""
    while not stop_event.is_set():
        # 每次循环发一个 chat + 一个 health
        tasks = [chat_mock(client, token, results)]
        if __import__("random").random() < 0.3:
            tasks.append(health_check(client, results))
        await asyncio.gather(*tasks)
        await asyncio.sleep(__import__("random").uniform(1, 4))


async def main():
    print(f"  并发压测: {CONCURRENT_USERS} 用户, {TEST_DURATION}s")
    print(f"  Health: {HEALTH_PATH}")
    print(f"  Chat:   {CHAT_PATH}")
    print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        token = await get_token(client)
        print(f"  Token: {token[:20]}...")

        results: list[dict] = []
        stop = asyncio.Event()

        workers = [
            user_worker(client, token, results, stop)
            for _ in range(CONCURRENT_USERS)
        ]

        task_group = asyncio.gather(*workers)

        # 运行指定时长
        await asyncio.sleep(TEST_DURATION)
        stop.set()
        await asyncio.wait_for(task_group, timeout=5)

    # 统计
    total = len(results)
    chats = [r for r in results if r["type"] == "chat" and r["status"] == 200]
    healths = [r for r in results if r["type"] == "health" and r["status"] == 200]
    failures = [r for r in results if r["status"] != 200]

    print(f"\n{'='*60}")
    print(f"  压测结果")
    print(f"{'='*60}")
    print(f"  总请求: {total}  |  成功: {total - len(failures)}  |  失败: {len(failures)}")
    print(f"  成功率: {(total - len(failures)) / max(total, 1):.1%}")
    print(f"  QPS:    {total / TEST_DURATION:.1f} req/s")
    print()

    def percentiles(vals, ps=[50, 95, 99]):
        s = sorted(vals)
        return {f"P{p}": s[int(len(s) * p / 100)] if s else 0 for p in ps}

    if chats:
        p = percentiles([c["latency_ms"] for c in chats])
        tp = percentiles([c["ttft_ms"] for c in chats if c["ttft_ms"]])
        print(f"  [Chat Mock] {len(chats)} 次")
        print(f"    总延迟: avg={sum(c['latency_ms'] for c in chats)/len(chats):.0f}ms "
              f"P50={p['P50']:.0f}ms P95={p['P95']:.0f}ms P99={p['P99']:.0f}ms")
        if tp:
            print(f"    TTFT:   avg={sum(c['ttft_ms'] for c in chats if c['ttft_ms'])/len([c for c in chats if c['ttft_ms']]):.0f}ms "
                  f"P50={tp['P50']:.0f}ms P95={tp['P95']:.0f}ms P99={tp['P99']:.0f}ms")

    if healths:
        p = percentiles([h["latency_ms"] for h in healths])
        print(f"  [Health] {len(healths)} 次")
        print(f"    延迟: avg={sum(h['latency_ms'] for h in healths)/len(healths):.0f}ms "
              f"P50={p['P50']:.0f}ms P95={p['P95']:.0f}ms P99={p['P99']:.0f}ms")

    if failures:
        print(f"\n  失败案例 ({len(failures)}):")
        for f in failures[:5]:
            print(f"    {f['type']} status={f['status']} {f.get('error','')[:80]}")

    print()
    print(f"{'='*60}")
    print(f"  简历话术建议")
    print(f"{'='*60}")
    chat_avg = sum(c['latency_ms'] for c in chats) / len(chats) if chats else 0
    chat_p95 = percentiles([c['latency_ms'] for c in chats])['P95'] if chats else 0
    print(f'  "使用 asyncio + httpx 进行 {CONCURRENT_USERS} 并发模拟压测，')
    print(f'   在 mock LLM 模式下系统吞吐量达 {total / TEST_DURATION:.1f} req/s，')
    print(f'   平均延迟 {chat_avg:.0f}ms，P95 延迟 {chat_p95:.0f}ms，')
    print(f'   验证了 FastAPI + LangGraph 异步链路的稳定性。"')


if __name__ == "__main__":
    asyncio.run(main())
