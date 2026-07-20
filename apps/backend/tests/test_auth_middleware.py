"""
认证与限流中间件单元测试

覆盖：
- AuthMiddleware: 无 token / 有效 token / 无效 token / 畸形 header / 豁免路径
- RateLimitMiddleware: 中间件层 429 响应、路径独立限流

注意：与 test_rate_limiter.py 的区别 - 本文件测试 RateLimitMiddleware.dispatch
中间件层行为（返回 429 JSONResponse），而非 _check_rate_limit 函数本身。
"""
import pytest
from types import SimpleNamespace
from starlette.datastructures import State

from app.core.middleware import (
    AuthMiddleware,
    RateLimitMiddleware,
    AUTH_EXEMPT_PATHS,
    _rate_buckets,
)

pytestmark = pytest.mark.unit


class MockRequest:
    """轻量请求桩 - 模拟 starlette.Request 被 middleware 用到的属性"""

    def __init__(self, path, auth_header=None, client_host="1.2.3.4"):
        self.url = SimpleNamespace(path=path)
        self.headers = {"authorization": auth_header} if auth_header else {}
        self.state = State()
        self.client = SimpleNamespace(host=client_host)


def _make_call_next(captured: dict):
    async def call_next(req):
        captured["user_id"] = getattr(req.state, "user_id", "__NOT_SET__")
        return SimpleNamespace(status_code=200, headers={})

    return call_next


class TestAuthMiddleware:
    """AuthMiddleware 认证策略 - 强制鉴权"""

    @pytest.mark.asyncio
    async def test_no_authorization_header_returns_401(self, monkeypatch):
        async def fake_validate(token):
            return "should-not-be-called"

        monkeypatch.setattr("app.core.middleware.validate_session_token", fake_validate)
        captured = {}
        mw = AuthMiddleware(app=None)
        resp = await mw.dispatch(MockRequest("/api/v1/products", auth_header=None), _make_call_next(captured))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_bearer_token_sets_user_id(self, monkeypatch):
        async def fake_validate(token):
            return "user-abc" if token == "valid-token" else None

        monkeypatch.setattr("app.core.middleware.validate_session_token", fake_validate)
        captured = {}
        mw = AuthMiddleware(app=None)
        await mw.dispatch(
            MockRequest("/api/v1/products", auth_header="Bearer valid-token"),
            _make_call_next(captured),
        )
        assert captured["user_id"] == "user-abc"

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, monkeypatch):
        async def fake_validate(token):
            return None

        monkeypatch.setattr("app.core.middleware.validate_session_token", fake_validate)
        captured = {}
        mw = AuthMiddleware(app=None)
        resp = await mw.dispatch(
            MockRequest("/api/v1/products", auth_header="Bearer bad-token"),
            _make_call_next(captured),
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_header_returns_401(self, monkeypatch):
        """无 Bearer 前缀的 header 被当作 token，验证失败返回 401"""
        validated_tokens = []

        async def fake_validate(token):
            validated_tokens.append(token)
            return None

        monkeypatch.setattr("app.core.middleware.validate_session_token", fake_validate)
        captured = {}
        mw = AuthMiddleware(app=None)
        resp = await mw.dispatch(
            MockRequest("/api/v1/products", auth_header="Token xyz"),
            _make_call_next(captured),
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_token_after_bearer_returns_401(self, monkeypatch):
        async def fake_validate(token):
            return "should-not-be-called"

        monkeypatch.setattr("app.core.middleware.validate_session_token", fake_validate)
        captured = {}
        mw = AuthMiddleware(app=None)
        resp = await mw.dispatch(
            MockRequest("/api/v1/products", auth_header="Bearer "),
            _make_call_next(captured),
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_exempt_paths_skip_auth(self, monkeypatch):
        called = {"validate": False}

        async def fake_validate(token):
            called["validate"] = True
            return None

        monkeypatch.setattr("app.core.middleware.validate_session_token", fake_validate)
        captured = {}
        mw = AuthMiddleware(app=None)
        for path in AUTH_EXEMPT_PATHS:
            await mw.dispatch(MockRequest(path, auth_header=None), _make_call_next(captured))
            assert captured["user_id"] == "__NOT_SET__"
            assert called["validate"] is False

    @pytest.mark.asyncio
    async def test_non_exempt_path_with_token_validates(self, monkeypatch):
        validated_tokens = []

        async def fake_validate(token):
            validated_tokens.append(token)
            return "user-xyz"

        monkeypatch.setattr("app.core.middleware.validate_session_token", fake_validate)
        captured = {}
        mw = AuthMiddleware(app=None)
        await mw.dispatch(
            MockRequest("/api/v1/cart", auth_header="Bearer my-token"),
            _make_call_next(captured),
        )
        assert validated_tokens == ["my-token"]
        assert captured["user_id"] == "user-xyz"


class TestRateLimitMiddlewareDispatch:
    """RateLimitMiddleware 中间件层 - 429 JSONResponse 行为

    与 test_rate_limiter.py 区别：后者测 _check_rate_limit 函数；
    本类测 RateLimitMiddleware.dispatch 返回 429 响应与路径隔离。
    """

    def setup_method(self):
        _rate_buckets.clear()

    @pytest.mark.asyncio
    async def test_first_request_allowed_returns_200(self):
        async def call_next(req):
            return SimpleNamespace(status_code=200, headers={})

        mw = RateLimitMiddleware(app=None)
        resp = await mw.dispatch(MockRequest("/api/v1/chat"), call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_over_limit_returns_429_with_envelope(self):
        async def call_next(req):
            return SimpleNamespace(status_code=200, headers={})

        mw = RateLimitMiddleware(app=None)
        path = "/api/v1/chat"
        for _ in range(10):
            await mw.dispatch(MockRequest(path), call_next)
        resp = await mw.dispatch(MockRequest(path), call_next)
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") is not None
        import json

        body = json.loads(resp.body)
        assert body["code"] == 4290
        assert body["data"] is None
        assert "message" in body

    @pytest.mark.asyncio
    async def test_different_paths_have_independent_limits(self):
        async def call_next(req):
            return SimpleNamespace(status_code=200, headers={})

        mw = RateLimitMiddleware(app=None)
        for _ in range(10):
            await mw.dispatch(MockRequest("/api/v1/chat"), call_next)
        resp_chat = await mw.dispatch(MockRequest("/api/v1/chat"), call_next)
        assert resp_chat.status_code == 429
        resp_upload = await mw.dispatch(MockRequest("/api/v1/upload/image"), call_next)
        assert resp_upload.status_code == 200
