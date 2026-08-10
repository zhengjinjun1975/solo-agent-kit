# -*- coding: utf-8 -*-
"""base.py — 统一工程基础设施（日志 / 原子写 / 并发锁 / 错误契约）。

P0 审查修复：日志缺失、原子写、并发锁、错误静默吞。
所有模块共用，避免重复实现。
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading

# ---- 日志（P0-2）----
# 内存日志缓冲（供前端日志诊断查看器）
_LOG_BUFFER = []
_LOG_BUFFER_LOCK = threading.Lock()
_LOG_BUFFER_MAX = 500


class MemoryLogHandler(logging.Handler):
    """收集最近 N 条日志到内存缓冲（前端日志诊断用）。"""

    def emit(self, record):
        try:
            msg = self.format(record)
            with _LOG_BUFFER_LOCK:
                _LOG_BUFFER.append({"ts": record.asctime, "level": record.levelname,
                                    "name": record.name, "msg": msg})
                if len(_LOG_BUFFER) > _LOG_BUFFER_MAX:
                    del _LOG_BUFFER[:len(_LOG_BUFFER) - _LOG_BUFFER_MAX]
        except Exception:
            pass


def get_logger(name: str) -> logging.Logger:
    """获取带统一格式的 logger。"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        # 加内存缓冲（日志诊断）
        mh = MemoryLogHandler()
        mh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(mh)
    return logger


def get_logs(limit: int = 100, level: str = None) -> list:
    """返回最近日志（供前端日志查看器）。level 过滤：INFO/WARN/ERROR。"""
    with _LOG_BUFFER_LOCK:
        logs = list(_LOG_BUFFER)
    if level:
        logs = [l for l in logs if l["level"] == level.upper()]
    return logs[-limit:]


# ---- 原子写（P0-1）----
def atomic_write(path: str, data) -> None:
    """原子写 JSON：写临时文件 + os.replace，崩溃不损坏原文件。"""
    dirname = os.path.dirname(path) or "."
    os.makedirs(dirname, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dirname, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            import json
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# ---- 并发锁（P0-1）----
class FileLock:
    """进程内文件访问锁（线程安全）。"""

    def __init__(self):
        self._lock = threading.Lock()


# 全局锁注册表：按路径加锁
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def lock_for(path: str) -> threading.Lock:
    """为路径获取（共享）锁，保证同一文件并发写安全。"""
    with _LOCKS_GUARD:
        if path not in _LOCKS:
            _LOCKS[path] = threading.Lock()
        return _LOCKS[path]


# ---- 错误契约（P0-3）----
class ApiError(Exception):
    """统一错误契约：携带面向客户端的 code + 非敏感 msg。"""

    def __init__(self, code: int = 400, msg: str = "请求失败", internal: str = ""):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.internal = internal  # 内部细节，不返回给客户端

    def to_dict(self) -> dict:
        return {"error": self.msg, "code": self.code}


class DataSourceError(ApiError):
    """数据源读取错误（替代静默返回 []）。"""

    def __init__(self, msg: str = "数据源读取失败", internal: str = ""):
        super().__init__(400, msg, internal)
