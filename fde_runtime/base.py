# -*- coding: utf-8 -*-
"""base.py — AtomicAgent 基类 + 生命周期状态机 + 信封 + CapabilityRegistry。

对齐生态原子化架构（域+原子/manifest/生命周期/组装器）与 CodeAgent 范式：
所有对外数据走 {ok:true,data:...} 或 {ok:false,error:...,[degraded:true]} 信封。
纯标准库，零第三方依赖。
"""
from __future__ import annotations

import abc


# ---- 生命周期状态机 ----
# DISCOVERED → RESOLVED → LOADED → REGISTERED → READY → RUNNING → UNLOADED
#                 └─ERROR┘  └─ERROR┘  └─ERROR┘   └─FALLBACK(降级)┘
_LEGAL_TRANSITIONS = {
    "DISCOVERED": {"RESOLVED", "ERROR"},
    "RESOLVED": {"LOADED", "ERROR"},
    "LOADED": {"REGISTERED", "ERROR"},
    "REGISTERED": {"READY", "ERROR"},
    "READY": {"RUNNING", "FALLBACK", "UNLOADED", "ERROR"},
    "RUNNING": {"READY", "FALLBACK", "ERROR"},
    "FALLBACK": {"READY", "UNLOADED", "ERROR"},
    "UNLOADED": {"ERROR"},
    "ERROR": set(),
}


class StateMachineError(Exception):
    """生命周期非法转移 / 状态机错误。"""


class StateMachine:
    """严格转移校验状态机。"""

    def __init__(self, initial: str = "DISCOVERED"):
        self._name = initial

    @property
    def name(self) -> str:
        return self._name

    def to(self, target: str) -> str:
        if target not in _LEGAL_TRANSITIONS.get(self._name, set()):
            raise StateMachineError(
                f"非法生命周期转移: {self._name} → {target}")
        self._name = target
        return self._name

    def assert_in(self, *names):
        if self._name not in names:
            raise StateMachineError(
                f"状态机当前为 {self._name}，期望 ∈ {names}")
        return True


# ---- 结果信封 ----
def ok(data=None):
    return {"ok": True, "data": data if data is not None else {}}


def fail(error: str, degraded: bool = False, **extra):
    env = {"ok": False, "error": error}
    if degraded:
        env["degraded"] = True
    env.update(extra)
    return env


# ---- 能力注册表 ----
class CapabilityRegistry:
    """能力 id → 原子名 索引（能力冲突检测）。"""

    def __init__(self):
        self._map = {}

    def add(self, atom_name: str, capability: str) -> None:
        if capability in self._map and self._map[capability] != atom_name:
            raise StateMachineError(
                f"能力冲突: {capability} 已被 {self._map[capability]} 占用，"
                f"{atom_name} 无法提供")
        self._map[capability] = atom_name

    def add_many(self, atom_name: str, capabilities) -> None:
        for c in capabilities or []:
            self.add(atom_name, c)

    def provider(self, capability: str) -> str:
        return self._map.get(capability)

    def has(self, capability: str) -> bool:
        return capability in self._map

    def all(self) -> dict:
        return dict(self._map)


class AtomicAgent(abc.ABC):
    """原子智能体基类。

    生命周期：DISCOVERED → RESOLVED → LOADED → REGISTERED → READY → RUNNING → UNLOADED。
    子类实现 load/register/run/unload 与接口自省。
    """

    def __init__(self, name: str, agent: str, version: str = "0.1.0",
                 open_source: bool = True, license: str = "Apache-2.0"):
        self.name = name
        self.agent = agent
        self.version = version
        self.open_source = open_source
        self.license = license
        self._sm = StateMachine()
        self._store = {}

    @property
    def state(self) -> str:
        return self._sm.name

    # ---- 生命周期 ----
    def load(self, ctx: dict = None) -> dict:
        if self._sm.name in ("DISCOVERED",):
            self._sm.to("RESOLVED")
        self._sm.to("LOADED")
        return ok({"name": self.name, "state": self.state})

    def register(self, reg: CapabilityRegistry) -> dict:
        reg.add_many(self.name, self.capabilities())
        self._sm.to("REGISTERED")
        return ok({"name": self.name, "capabilities": self.capabilities()})

    def run(self, **params) -> dict:
        # 允许独立自测直接 run（自动推进到 READY），且支持多次 run（回到 READY 再 RUNNING）
        if self._sm.name == "LOADED":
            self._sm.to("REGISTERED")
        if self._sm.name in ("REGISTERED", "RUNNING", "FALLBACK"):
            self._sm.to("READY")
        try:
            self._sm.to("RUNNING")
            return self._run(**params)
        except Exception as e:  # noqa: BLE001
            self._sm.to("FALLBACK")
            return fail(f"{self.name} 运行异常: {e}", degraded=True)

    @abc.abstractmethod
    def _run(self, **params) -> dict:
        """子类实现核心逻辑（经 self._store / 复用的现有模块核心）。"""

    def unload(self, ctx: dict = None) -> dict:
        self._sm.to("UNLOADED")
        return ok({"name": self.name, "state": self.state})

    # ---- 接口自省 ----
    def capabilities(self) -> list:
        return []

    def inputs(self) -> dict:
        return {}

    def outputs(self) -> dict:
        return {}

    def depends_on(self) -> list:
        return []

    # ---- 帮助 ----
    def set_store(self, key, value) -> None:
        self._store[key] = value

    def get_store(self, key, default=None):
        return self._store.get(key, default)
