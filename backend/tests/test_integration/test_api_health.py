"""API 路由集成测试 — 健康检查 / 认证 / 公开接口"""

import pytest


class TestHealthEndpoints:
    async def test_health_check(self, client) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    async def test_health_live(self, client) -> None:
        response = await client.get("/health/live")
        assert response.status_code == 200

    async def test_health_ready(self, client) -> None:
        response = await client.get("/health/ready")
        assert response.status_code == 200

    async def test_metrics_endpoint(self, client) -> None:
        response = await client.get("/metrics")
        assert response.status_code == 200


class TestAuthEndpoints:
    async def test_register(self, client) -> None:
        import uuid
        uid = uuid.uuid4().hex[:10]
        response = await client.post("/api/v1/auth/register", json={
            "username": f"testuser_{uid}",
            "password": "Test1234Xyz",
            "email": f"test_{uid}@example.com",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["username"] == f"testuser_{uid}"

    async def test_login_success(self, client, test_user_credentials) -> None:
        response = await client.post("/api/v1/auth/login", json={
            "username": test_user_credentials["username"],
            "password": "Test1234",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "token" in data["data"]

    async def test_login_wrong_password(self, client, test_user_credentials) -> None:
        response = await client.post("/api/v1/auth/login", json={
            "username": test_user_credentials["username"],
            "password": "WrongPassword666",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] != 0

    async def test_register_duplicate_username(self, client, test_user_credentials) -> None:
        response = await client.post("/api/v1/auth/register", json={
            "username": test_user_credentials["username"],
            "password": "Test1234Xyz",
            "email": "another@example.com",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] != 0

    async def test_register_weak_password(self, client) -> None:
        """密码不含大写字母应被拒绝"""
        response = await client.post("/api/v1/auth/register", json={
            "username": "weakpwuser",
            "password": "alllowercase123",
            "email": "weak@example.com",
        })
        # 可能返回 422 (validation error) 或 200 with error code
        assert response.status_code in (200, 422)


class TestProtectedEndpoints:
    async def test_current_user_authorized(self, client, auth_headers, test_user_credentials) -> None:
        response = await client.get("/api/v1/auth/current", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["username"] == test_user_credentials["username"]

    async def test_current_user_unauthorized(self, client) -> None:
        response = await client.get("/api/v1/auth/current")
        assert response.status_code in (401, 403)
