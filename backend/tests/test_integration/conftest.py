"""集成测试 fixtures — 使用真实 PostgreSQL / Redis / ChromaDB"""

import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from src.core.database import async_session_factory


@pytest.fixture(scope="module")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture(scope="module")
async def test_user_credentials() -> dict:
    import uuid
    from src.core.password_utils import hash_password
    from src.core.redis_client import TOKEN_EXPIRE_SECONDS, TOKEN_PREFIX, get_redis
    from src.models.user import User

    uid = uuid.uuid4().hex[:16]
    username = f"test_{uid[:8]}"

    async with async_session_factory() as session:
        async with session.begin():
            user = User(
                user_id=uid, username=username, nickname="测试用户",
                email=f"test_{uid[:8]}@example.com",
                password=hash_password("Test1234"),
                roles="READ_WRITE", permissions="",
            )
            session.add(user)
            await session.flush()
            await session.refresh(user)

    # 将 token 写入 Redis（模拟登录状态），避免中间件认证失败
    from src.core.jwt_utils import create_token
    token = create_token(uid, username, "READ_WRITE")
    try:
        redis = await get_redis()
        await redis.set(f"{TOKEN_PREFIX}{uid}", token, ex=TOKEN_EXPIRE_SECONDS)
    except Exception:
        pass

    return {"user_id": uid, "username": username, "password": "Test1234", "token": token}


@pytest_asyncio.fixture(scope="module")
async def auth_headers(test_user_credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {test_user_credentials['token']}"}
