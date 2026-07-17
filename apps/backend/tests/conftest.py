"""
pytest fixtures - async HTTP client, mock LLM/DB/cache, sample data
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest_asyncio.fixture
async def client():
    """异步 HTTP 测试客户端 - 使用 ASGITransport 直接调用 ASGI app"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_check():
    """检查数据库是否可用。不可用时标记测试为 skip。"""
    from app.core.database import engine
    from sqlalchemy import text
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        pytest.skip("Database unavailable - running in degraded mode")


@pytest.fixture
def mock_llm(monkeypatch):
    """Mock LLM 调用，返回预设响应，防止测试 hang

    用法:
        def test_something(mock_llm):
            mock_llm.set_chat_response("推荐商品...")
            # 调用会返回预设响应，不会真正请求 API
    """
    class MockLLM:
        def __init__(self):
            self._chat_response = ""
            self._fast_chat_response = ""
            self._stream_chunks: list[str] = []
            self._calls: list[dict] = []

        def set_chat_response(self, text: str):
            self._chat_response = text

        def set_fast_chat_response(self, text: str):
            self._fast_chat_response = text

        def set_stream_chunks(self, chunks: list[str]):
            self._stream_chunks = chunks

        @property
        def call_count(self):
            return len(self._calls)

        async def chat_completion(self, messages, **kwargs):
            self._calls.append({"messages": messages, **kwargs})
            return self._chat_response

        async def fast_chat_completion(self, messages, **kwargs):
            self._calls.append({"messages": messages, **kwargs})
            return self._fast_chat_response

    mock = MockLLM()

    async def _fake_chat(*args, **kwargs):
        return await mock.chat_completion(*args, **kwargs)

    async def _fake_fast_chat(*args, **kwargs):
        return await mock.fast_chat_completion(*args, **kwargs)

    monkeypatch.setattr("app.services.llm_client.chat_completion", _fake_chat)
    monkeypatch.setattr("app.services.llm_client.fast_chat_completion", _fake_fast_chat)
    return mock


@pytest.fixture
def mock_cache():
    """NoOpCache - 测试中不产生缓存副作用"""
    from app.core.cache.backend import NoOpCache
    return NoOpCache()


@pytest.fixture
def sample_product():
    """标准 Product dict - 基于 287 条商品中的典型数据"""
    return {
        "id": "test-001",
        "title": "无糖薄荷糖清新口气薄荷糖",
        "description": "0糖0脂0卡薄荷糖，清新口气，便携小包装",
        "price": 9.9,
        "category": "食品饮料",
        "brand": "都市草园",
        "rating": 4.8,
        "rating_count": 1520,
        "sales": 3000,
        "tags": ["无糖", "薄荷糖", "清新口气", "便携"],
        "highlights": ["0糖0脂0卡", "清新口气", "便携小包装"],
        "scenarios": ["日常", "社交", "办公"],
        "attributes": {"口味": "薄荷", "包装": "袋装", "规格": "30g"},
        "image_urls": ["https://example.com/img1.jpg"],
        "stock": 100,
        "source_product_id": "SP-001",
    }


@pytest.fixture
def sample_cart_item():
    """标准 CartItem dict"""
    return {
        "product_id": "test-001",
        "title": "无糖薄荷糖清新口气薄荷糖",
        "price": 9.9,
        "quantity": 2,
    }
