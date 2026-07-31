"""core/password_utils.py 密码工具测试"""

import bcrypt

from src.core.password_utils import hash_password, verify_password


class TestHashPassword:
    def test_returns_string(self) -> None:
        result = hash_password("hello123")
        assert isinstance(result, str)
        assert len(result) > 20

    def test_different_salts(self) -> None:
        """相同密码两次哈希应产生不同结果"""
        h1 = hash_password("hello123")
        h2 = hash_password("hello123")
        assert h1 != h2

    def test_empty_password(self) -> None:
        result = hash_password("")
        assert isinstance(result, str)

    def test_unicode_password(self) -> None:
        result = hash_password("密码123!@#")
        assert isinstance(result, str)


class TestVerifyPassword:
    def test_correct_password(self) -> None:
        hashed = hash_password("secret")
        assert verify_password("secret", hashed) is True

    def test_wrong_password(self) -> None:
        hashed = hash_password("secret")
        assert verify_password("wrong", hashed) is False

    def test_empty_password(self) -> None:
        hashed = hash_password("")
        assert verify_password("", hashed) is True

    def test_case_sensitive(self) -> None:
        hashed = hash_password("Password")
        assert verify_password("password", hashed) is False
