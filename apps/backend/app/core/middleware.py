"""
中间件 - request_id 注入、请求日志、认证、限流
遵循开发规约 v2.0 §15
"""
import time
import uuid
import logging
from collections import defaultdict, deque
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.auth_service import validate_session_token
from app.schemas.common import ApiResponse

logger = logging.getLogger("middleware")

# 认证豁免路径 - 仅这些路径不需要 token
AUTH_EXEMPT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/health",
    "/ready",
    "/version",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
    "/",
}

# 限流配置：路径 -> (window_seconds, max_requests)
RATE_LIMIT_CONFIG = {
    "/api/v1/chat": (60, 10),          # 10 req/min
    "/api/v1/voice/recognize": (60, 10),
    "/api/v1/voice/chat": (60, 10),
    "/api/v1/upload/vision-search": (60, 10),
    "/api/v1/upload/image": (60, 20),
    "/api/v1/evaluation/run": (300, 3),  # 3 req/5min
}

# 内存限流器：client_key:path -> deque[timestamps]
_rate_buckets: dict[str, deque] = defaultdict(deque)


def _check_rate_limit(key: str, window: int, max_req: int) -> tuple[bool, int]:
    """检查限流。返回 (allowed, remaining_seconds)."""
    now = time.time()
    bucket = _rate_buckets[key]
    # 清除过期记录
    while bucket and bucket[0] < now - window:
        bucket.popleft()
    if len(bucket) >= max_req:
        # 计算还需要等多久
        retry_after = int(bucket[0] + window - now) + 1
        return False, max(retry_after, 1)
    bucket.append(now)
    return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件 - 针对 LLM/上传等敏感端点"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        limit_config = RATE_LIMIT_CONFIG.get(path)

        if limit_config is not None:
            window, max_req = limit_config
            # 以 IP 为 key（过渡期无 user_id）
            client_ip = request.client.host if request.client else "unknown"
            rate_key = f"{client_ip}:{path}"

            allowed, retry_after = _check_rate_limit(rate_key, window, max_req)
            if not allowed:
                logger.warning("Rate limit hit: %s %s (retry after %ds)", client_ip, path, retry_after)
                return JSONResponse(
                    status_code=429,
                    content=ApiResponse(
                        code=4290,
                        message=f"请求过于频繁，请 {retry_after} 秒后重试",
                        data=None,
                    ).model_dump(),
                    headers={"Retry-After": str(retry_after)},
                )

        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求注入唯一 request_id"""
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "[%s] %s %s -> %d (%.1fms)",
            request_id, request.method, request.url.path,
            response.status_code, duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """Session Token 认证中间件

    策略：
    - 静态资源/非 API 路径：直接放行
    - 豁免路径（AUTH_EXEMPT_PATHS）：直接放行
    - 其他 /api/ 路径：必须携带有效 token，否则返回 401
    """
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 静态资源豁免
        if not path.startswith("/api/") and not path.startswith("/auth"):
            return await call_next(request)

        # 明确豁免
        if path in AUTH_EXEMPT_PATHS:
            return await call_next(request)

        # 提取 token
        auth_header = request.headers.get("authorization", "")
        token = auth_header.replace("Bearer ", "").strip() if auth_header else ""

        if not token:
            return JSONResponse(
                status_code=401,
                content=ApiResponse(
                    code=4010,
                    message="未提供认证令牌，请先登录",
                    data=None,
                ).model_dump(),
            )

        # 验证 token
        user_id = await validate_session_token(token)
        if not user_id:
            return JSONResponse(
                status_code=401,
                content=ApiResponse(
                    code=4011,
                    message="认证令牌无效或已过期，请重新登录",
                    data=None,
                ).model_dump(),
            )

        request.state.user_id = user_id
        return await call_next(request)
