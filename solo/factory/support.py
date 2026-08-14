# -*- coding: utf-8 -*-
"""support.py — 工单运维能力面（工单状态机 + 监控告警 + 运维知识库）。

单一概念域：把 FDE 现场的「发现问题 → 建单 → 处理 → 解决 → 沉淀」走成闭环。

复用（极简，不重造）：
- task.Task.new_issue / diagnose / resolve_issue / list_issues   工单状态机（状态持久化）
- ops.monitor_devices()                                          监控采集 → 异常自动建单
- memory.Memory.add_fact / search                                运维知识库（问题→解决 沉淀）

零额外依赖（纯标准库 + 已有 solo 模块）。
"""
from __future__ import annotations

import os

from solo import task as task_mod
from solo import memory as memory_mod
from . import ops as ops_mod

DEFAULT_TICKET_DIR = os.path.join(os.path.expanduser("~"), ".solo", "tickets")
DEFAULT_KB_DIR = os.path.join(os.path.expanduser("~"), ".solo", "ops_kb")

# 告警阈值（确定性常量，可调整）
ALARM_THRESHOLDS = {"cpu_percent": 85.0, "mem_percent": 90.0}

# 工单状态（对外中文状态；内部复用 task 状态机并映射）
TICKET_STATES = ("新建", "处理中", "已解决", "关闭")
_TASK_TO_STATE = {
    "open": "新建", "diagnosed": "处理中", "doing": "处理中",
    "waiting": "处理中", "resolved": "已解决", "closed": "关闭",
}


# ═══════════════════════════ 1. 工单状态机（复用 task）═══════════════════════════
class SupportTicket:
    """工单运维状态机：新建 → 处理中 → 已解决/关闭。

    底层复用 task.Task（new_issue/diagnose/resolve_issue），状态持久化到文件。
    """

    def __init__(self, dir: str = DEFAULT_TICKET_DIR):
        self.dir = dir
        self._task = task_mod.Task(dir)

    def new(self, problem: str, severity: str = "medium") -> dict:
        """新建工单（自动 triage 分类）。severity: low/medium/high/critical。"""
        t = self._task.new_issue(problem, severity=severity)
        return self._view(t)

    def process(self, tid: str, action: str) -> dict:
        """处理中：记录处理动作（进诊断/处理）。"""
        t = self._task.status(tid)
        if "problem" not in t:
            return {"error": "工单不存在", "id": tid}
        if t.get("state") in ("resolved", "closed"):
            return {"error": "工单已终结，不能重新处理", "id": tid}
        self._task.diagnose(tid, action)
        return self._view(self._task.status(tid))

    def resolve(self, tid: str, resolution: str) -> dict:
        """已解决：记录解决方案（同时沉淀进知识库）。"""
        t = self._task.status(tid)
        if "problem" not in t:
            return {"error": "工单不存在", "id": tid}
        resolved = self._task.resolve_issue(tid, resolution)
        self._kb_note(t.get("problem", ""), resolution)
        return self._view(resolved)

    def close(self, tid: str) -> dict:
        """关闭：终结工单。"""
        t = self._task.status(tid)
        if "problem" not in t:
            return {"error": "工单不存在", "id": tid}
        self._task.set_state(tid, "closed", note="工单关闭")
        return self._view(self._task.status(tid))

    def status(self, tid: str) -> dict:
        return self._view(self._task.status(tid))

    def list(self, state: str = None) -> list:
        """列出工单。state: 新建/处理中/已解决/关闭（None=全部）。"""
        issues = self._task.list_issues()
        out = []
        for i in issues:
            st = _TASK_TO_STATE.get(i.get("state"), i.get("state", ""))
            if state is None or st == state:
                out.append({**i, "state": st})
        return out

    # ---- 内部 ----
    def _view(self, t: dict) -> dict:
        if not isinstance(t, dict):
            return t
        if "problem" not in t and "error" in t:
            return t
        return {**t, "state": _TASK_TO_STATE.get(t.get("state"), t.get("state", ""))}

    def _kb_note(self, problem: str, resolution: str) -> None:
        """解决后自动沉淀知识库（复用 memory，失败静默）。"""
        try:
            KnowledgeBase(self._kb_dir()).add(problem, resolution)
        except Exception:  # noqa: BLE001
            pass

    def _kb_dir(self) -> str:
        # 与工单同目录下的 kb 子目录（隔离，避免污染全局记忆）
        return os.path.join(self.dir, "kb")


# ═══════════════════════════ 2. 监控告警 → 自动建单（复用 ops）═══════════════════════════
def alarm_tickets(monitor: dict = None, thresholds: dict = None) -> dict:
    """基于监控异常自动生成工单。

    monitor: ops.monitor_devices() 结果；None 则现场采集一次。
    thresholds: {cpu_percent, mem_percent}，缺省 ALARM_THRESHOLDS。
    返回 {created, tickets, alarms}。
    """
    thr = {**ALARM_THRESHOLDS, **(thresholds or {})}
    if monitor is None:
        monitor = ops_mod.monitor_devices()
    if not monitor.get("ok"):
        return {"created": [], "tickets": [], "alarms": [],
                "error": monitor.get("error", "无设备台账")}
    st = SupportTicket()
    created, alarms = [], []
    for d in monitor.get("devices", []):
        name = d.get("name", "设备")
        if not d.get("ok"):
            reason = f"设备 {name} 连接/采集失败: {d.get('error', '')}"
            alarms.append({"device": name, "type": "connection", "reason": reason})
            created.append(st.new(reason, severity="high"))
            continue
        cpu = d.get("cpu_percent")
        mem = d.get("mem_percent")
        if cpu is not None and cpu > thr["cpu_percent"]:
            reason = f"设备 {name} CPU 占用 {cpu}% 超阈值 {thr['cpu_percent']}%"
            alarms.append({"device": name, "type": "cpu", "value": cpu, "reason": reason})
            created.append(st.new(reason, severity="medium"))
        if mem is not None and mem > thr["mem_percent"]:
            reason = f"设备 {name} 内存占用 {mem}% 超阈值 {thr['mem_percent']}%"
            alarms.append({"device": name, "type": "mem", "value": mem, "reason": reason})
            created.append(st.new(reason, severity="medium"))
    return {"created": len(created), "tickets": created, "alarms": alarms}


# ═══════════════════════════ 3. 运维知识库（复用 memory）═══════════════════════════
class KnowledgeBase:
    """运维知识库：问题→解决 沉淀（复用 memory.Memory 事实层）。

    底层复用 memory.Memory.add_fact / search（含去重、可语义检索）。
    """

    def __init__(self, dir: str = DEFAULT_KB_DIR):
        self.mem = memory_mod.Memory(dir)

    def add(self, problem: str, solution: str) -> bool:
        """沉淀一条经验：'问题 → 解决'（复用 memory 事实层，去重）。"""
        text = f"{problem} → {solution}"
        return self.mem.add_fact(text, tags=["ops-kb"])

    def search(self, problem: str, top_k: int = 3) -> list:
        """按问题检索历史解决方案（复用 memory.search 语义检索）。"""
        return self.mem.search(problem, top_k=top_k)

    def all(self) -> list:
        """列出全部沉淀经验。"""
        return self.mem._load(self.mem._facts_path, [])
