"""通用懒加载单例 - 统一 5 处重复的模块级单例模式

用法:
    # 定义
    my_model = LazySingleton(lambda: load_model(), retry_on_fail=True, cooldown=300)

    # 使用
    instance = my_model.get()       # 返回 T | None
    my_model.is_loaded()            # 是否已加载
    my_model.set_instance(model)    # 依赖注入 (startup.py 用)
    my_model.reset()                # 重置，下次 get 重新初始化
"""
import threading
import time
import logging
from typing import Callable, Generic, TypeVar

logger = logging.getLogger("lazy")

T = TypeVar("T")

_UNINIT = object()


class LazySingleton(Generic[T]):
    """线程安全懒加载单例，支持失败重试和依赖注入"""

    def __init__(
        self,
        factory: Callable[[], T],
        retry_on_fail: bool = False,
        cooldown: int = 300,
    ):
        self._factory = factory
        self._instance: T | object = _UNINIT
        self._lock = threading.Lock()
        self._retry_on_fail = retry_on_fail
        self._cooldown = cooldown
        self._failed_at: float = 0

    def get(self) -> T | None:
        """返回实例，未初始化或加载失败时返回 None"""
        if self._instance is not _UNINIT and self._instance is not None:
            return self._instance  # type: ignore[return-value]

        with self._lock:
            # 双重检查
            if self._instance is not _UNINIT and self._instance is not None:
                return self._instance  # type: ignore[return-value]

            # 失败冷却检查
            if self._instance is None and not self._retry_on_fail:
                return None
            if self._instance is None and self._retry_on_fail:
                if time.monotonic() - self._failed_at < self._cooldown:
                    return None

            # 首次或重试加载
            try:
                self._instance = self._factory()
                return self._instance  # type: ignore[return-value]
            except Exception as e:
                logger.warning("LazySingleton load failed: %s", e)
                self._instance = None
                self._failed_at = time.monotonic()
                return None

    def is_loaded(self) -> bool:
        """是否已成功加载"""
        return self._instance is not _UNINIT and self._instance is not None

    def reset(self) -> None:
        """重置状态，下次 get 会重新初始化"""
        with self._lock:
            self._instance = _UNINIT

    def set_instance(self, instance: T) -> None:
        """依赖注入 - 外部已创建好实例时直接设置"""
        with self._lock:
            self._instance = instance
