# -*- coding: utf-8 -*-
"""diagnostics.py — 环境诊断（P1-2 下沉，解除 agent→web 反向依赖）。

从 web_server 下沉：_setup_checks 的通用诊断逻辑，agent/cli/web 共用。
"""
from __future__ import annotations

import json
import os
import sys

from solo import provider as provider_mod
from solo import memory as memory_mod


def check_environment() -> dict:
    """环境诊断：Python / Ollama / config / 记忆库。"""
    checks = {}
    checks["python"] = {"ok": sys.version_info >= (3, 9),
                        "version": f"{sys.version_info.major}.{sys.version_info.minor}"}
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            models = [m.get("name", "") for m in json.load(r).get("models", [])]
        checks["ollama"] = {"ok": True, "models": models[:5]}
    except Exception:
        checks["ollama"] = {"ok": False, "error": "本地 Ollama 未运行"}
    cfg = provider_mod.load_config()
    checks["config"] = {"ok": bool(cfg), "has_provider_yaml": bool(cfg)}
    m = memory_mod.Memory()
    checks["memory"] = {"ok": True, "dir": m.dir,
                        "facts": len(m._load(m._facts_path, []))}
    return {"checks": checks,
            "all_ok": all(c.get("ok", True) for c in checks.values())}
