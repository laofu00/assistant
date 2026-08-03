"""Locust 性能压测脚本

用法：
  cd backend && .venv/Scripts/locust -f tests/locustfile.py --host=http://localhost:8000 \
      --headless --users 20 --spawn-rate 5 --run-time 60s

前置条件：
    1. 后端服务已启动
    2. 测试用户已注册: python tests/locustfile.py --setup
"""

import json
import logging
import os
import random
import sys
import time

import requests
from locust import HttpUser, between, events, task

# ==================== 配置 ====================

USE_MOCK = os.environ.get("USE_MOCK", "true").lower() == "true"
CHAT_PATH = "/api/v1/chat/mock" if USE_MOCK else "/api/v1/chat"
MODE_LABEL = "mock" if USE_MOCK else "real"

TEST_USERNAME = "testuser"
TEST_PASSWORD = "Test123456"
BASE_URL = os.environ.get("LOCUST_HOST", "http://localhost:8000")

QUERIES = [
    "什么是 RAG？",
    "LangGraph 的 Checkpointer 有什么作用？",
    "工具注册中心支持哪三种权限级别？",
    "短期记忆保留多少条对话？",
]

# 全局 token：在 init 事件中登录一次，所有用户共享
TOKEN = ""
HEADERS = {}


def setup_test_user():
    """注册测试用户（如果不存在）并获取 token"""
    print("注册/登录测试用户...")
    # 先尝试登录
    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": TEST_USERNAME, "password": TEST_PASSWORD,
    }, timeout=10)
    if r.status_code == 200:
        token = r.json().get("data", {}).get("token", "")
        print(f"  登录成功, token={token[:16]}...")
        return token

    # 注册
    r = requests.post(f"{BASE_URL}/api/v1/auth/register", json={
        "username": TEST_USERNAME, "password": TEST_PASSWORD,
    }, timeout=10)
    if r.status_code != 200:
        print(f"  注册失败: {r.status_code} {r.text}")
        sys.exit(1)
    print(f"  注册成功: {r.json()}")

    # 再登录
    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": TEST_USERNAME, "password": TEST_PASSWORD,
    }, timeout=10)
    if r.status_code != 200:
        print(f"  登录失败: {r.status_code}")
        sys.exit(1)
    token = r.json().get("data", {}).get("token", "")
    print(f"  登录成功, token={token[:16]}...")
    return token


class SmartAssistantUser(HttpUser):
    wait_time = between(3, 10)
    # SSE 流式连接需要更长超时
    network_timeout = 30.0

    def on_start(self):
        if not TOKEN:
            logging.error("token 未初始化")

    @task(2)
    def health_check(self):
        with self.client.get("/health/live", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(5)
    def chat_mock(self):
        if not TOKEN:
            return
        query = random.choice(QUERIES)
        with self.client.post(
            CHAT_PATH,
            json={"message": query, "user_id": TEST_USERNAME},
            headers=HEADERS,
            catch_response=True,
            stream=True,
            timeout=30,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return

            # 快速消费 SSE 流
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: ") and line[6:].strip() == "[DONE]":
                    break
            resp.success()


# ==================== 事件钩子 ====================

@events.init.add_listener
def on_init(environment, **kwargs):
    global TOKEN, HEADERS
    TOKEN = setup_test_user()
    HEADERS = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    print(f"\n{'='*60}")
    print(f"  Locust | {MODE_LABEL.upper()} | {CHAT_PATH}")
    print(f"{'='*60}\n")


@events.quitting.add_listener
def on_quit(environment, **kwargs):
    stats = environment.stats
    total = stats.total.num_requests
    failures = stats.total.num_failures
    avg = stats.total.avg_response_time
    p50 = stats.total.get_response_time_percentile(0.50)
    p95 = stats.total.get_response_time_percentile(0.95)
    p99 = stats.total.get_response_time_percentile(0.99)
    elapsed = max(stats.total.last_request_timestamp - stats.total.start_time, 1)
    rps = total / elapsed

    print(f"\n{'='*60}")
    print(f"  压测结果 ({MODE_LABEL.upper()})")
    print(f"{'='*60}")
    print(f"  总请求:  {total}    失败: {failures}")
    print(f"  成功率:  {(1 - failures/max(total,1)):.1%}")
    print(f"  平均QPS: {rps:.1f} req/s")
    print(f"  延迟 P50: {p50:.0f}ms   P95: {p95:.0f}ms   P99: {p99:.0f}ms")
    print(f"  平均延迟: {avg:.0f}ms")
    print(f"{'='*60}")
    if USE_MOCK:
        print("  注: mock LLM 模式，排除外部 API 延迟。")
    print()

    # 分接口统计
    print(f"   {'接口':<30s} {'请求数':>8s} {'失败率':>8s} {'P50':>8s} {'P95':>8s}")
    for entry in stats.entries.values():
        if entry.num_requests == 0:
            continue
        fail_rate = entry.num_failures / entry.num_requests
        p50e = entry.get_response_time_percentile(0.50) or 0
        p95e = entry.get_response_time_percentile(0.95) or 0
        print(f"   {entry.name:<30s} {entry.num_requests:>8d} {fail_rate:>7.1%} {p50e:>7.0f}ms {p95e:>7.0f}ms")
    print()


# 支持直接运行: python tests/locustfile.py --setup
if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup_test_user()
    else:
        print("用法: locust -f tests/locustfile.py --host=http://localhost:8000")
        print("或:   python tests/locustfile.py --setup  # 注册测试用户")
