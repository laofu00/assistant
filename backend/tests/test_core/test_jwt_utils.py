"""core/jwt_utils.py JWT 工具测试"""

from unittest.mock import patch

import jwt
import pytest

from src.core.jwt_utils import create_token, get_user_id_from_token, verify_token


class TestCreateToken:
    def test_returns_string(self) -> None:
        token = create_token("user123", "testuser")
        assert isinstance(token, str)
        assert len(token) > 50

    def test_token_contains_claims(self) -> None:
        token = create_token("user123", "testuser")
        decoded = jwt.decode(token, "smart-assistant-jwt-secret-key-change-in-production", algorithms=["HS256"])
        assert decoded["sub"] == "user123"
        assert decoded["username"] == "testuser"
        assert decoded["roles"] == "READ_WRITE"
        assert "iat" in decoded
        assert "exp" in decoded

    def test_exp_is_future(self) -> None:
        from datetime import datetime, timezone
        token = create_token("user123", "testuser")
        decoded = jwt.decode(token, "smart-assistant-jwt-secret-key-change-in-production", algorithms=["HS256"])
        now = datetime.now(timezone.utc).timestamp()
        assert decoded["exp"] > now


class TestVerifyToken:
    def test_valid_token(self) -> None:
        token = create_token("user123", "testuser")
        payload = verify_token(token)
        assert payload["sub"] == "user123"
        assert payload["username"] == "testuser"

    def test_invalid_token(self) -> None:
        with pytest.raises(jwt.PyJWTError):
            verify_token("invalid.token.here")

    def test_empty_token(self) -> None:
        with pytest.raises(jwt.PyJWTError):
            verify_token("")


class TestGetUserIdFromToken:
    def test_valid_token(self) -> None:
        token = create_token("user456", "another")
        user_id = get_user_id_from_token(token)
        assert user_id == "user456"

    def test_invalid_token(self) -> None:
        user_id = get_user_id_from_token("bad.token")
        assert user_id is None

    def test_token_without_sub(self) -> None:
        """payload 不含 sub 字段时应返回 None"""
        # 直接用 jwt.encode 生成一个无 sub 的 token
        from datetime import datetime, timedelta, timezone
        payload = {
            "username": "test",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        }
        token = jwt.encode(payload, "smart-assistant-jwt-secret-key-change-in-production", algorithm="HS256")
        user_id = get_user_id_from_token(token)
        assert user_id is None
