"""
统一异常定义 - 错误码体系 4xxx/5xxx
遵循开发规约 v2.0 §14
"""
from fastapi import HTTPException


class AppException(HTTPException):
    """应用级异常基类"""
    def __init__(self, code: int, message: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail={"code": code, "message": message, "data": None})


# ── 客户端错误 4xxx ──
class BadRequestError(AppException):
    def __init__(self, message: str = "请求参数错误"):
        super().__init__(code=4000, message=message, status_code=400)


class NotFoundError(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=4004, message=message, status_code=404)


class ValidationError(AppException):
    def __init__(self, message: str = "输入验证失败"):
        super().__init__(code=4220, message=message, status_code=422)


class AuthError(AppException):
    def __init__(self, message: str = "认证失败"):
        super().__init__(code=4010, message=message, status_code=401)


class RateLimitError(AppException):
    def __init__(self, message: str = "请求过于频繁"):
        super().__init__(code=4290, message=message, status_code=429)


# ── 服务端错误 5xxx ──
class LLMServiceError(AppException):
    def __init__(self, message: str = "LLM 服务不可用"):
        super().__init__(code=5001, message=message, status_code=503)


class RAGServiceError(AppException):
    def __init__(self, message: str = "检索服务暂不可用"):
        super().__init__(code=5002, message=message, status_code=503)


class DatabaseError(AppException):
    def __init__(self, message: str = "数据库异常"):
        super().__init__(code=5003, message=message, status_code=500)


class DatabaseUnavailableError(AppException):
    def __init__(self, message: str = "数据库未配置或不可用"):
        super().__init__(code=5004, message=message, status_code=503)


class LLMProviderError(AppException):
    def __init__(self, message: str = "LLM Provider 错误"):
        super().__init__(code=5005, message=message, status_code=502)


class RetrieverError(AppException):
    def __init__(self, message: str = "检索引擎错误"):
        super().__init__(code=5006, message=message, status_code=500)
