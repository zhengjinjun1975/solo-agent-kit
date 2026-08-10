# -*- coding: utf-8 -*-
"""monitor.py — 环境监控（对标 FDE 现场资源监控，轻量零依赖）。

FDE 现场每天看资源：CPU / 内存 / 磁盘 / 进程 / 网络。
用标准库实现基础采集（优先），psutil 可选增强。

方法：psutil 可用 → 全量；否则标准库降级（CPU负载/磁盘/进程数）。
"""
from __future__ import annotations

import os


def system_stats() -> dict:
    """采集系统资源状态（FDE 监控看板数据）。"""
    stats = {"cpu": _cpu(), "memory": _memory(), "disk": _disk(),
             "processes": _processes(), "host": _host()}
    return stats


def _cpu() -> dict:
    try:
        import psutil
        return {"percent": psutil.cpu_percent(interval=0.5),
                "cores": psutil.cpu_count(logical=True),
                "load": os.getloadavg() if hasattr(os, "getloadavg") else None}
    except ImportError:
        # 标准库降级：仅负载
        load = os.getloadavg() if hasattr(os, "getloadavg") else None
        return {"percent": None, "cores": None, "load": load}


def _memory() -> dict:
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {"total": vm.total, "used": vm.used, "percent": vm.percent}
    except ImportError:
        return {"total": None, "used": None, "percent": None}


def _disk() -> dict:
    try:
        import psutil
        parts = []
        for p in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(p.mountpoint)
                parts.append({"mount": p.mountpoint, "total": u.total,
                              "used": u.used, "percent": u.percent})
            except OSError:
                continue
        return {"parts": parts}
    except ImportError:
        return {"parts": []}


def _processes() -> dict:
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                procs.append({"pid": info["pid"], "name": info["name"],
                              "cpu": round(info.get("cpu_percent") or 0, 1),
                              "mem": round(info.get("memory_percent") or 0, 2)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: -x["cpu"])
        return {"count": len(procs), "top": procs[:10]}
    except ImportError:
        return {"count": None, "top": []}


def _host() -> dict:
    return {"platform": os.name,
            "cwd": os.getcwd()}


def top_processes(limit: int = 10) -> list:
    """按 CPU 排序的 Top 进程（FDE 定位高占用）。"""
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
            try:
                info = p.info
                procs.append({"pid": info["pid"], "name": info["name"],
                              "cpu": round(info.get("cpu_percent") or 0, 1)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: -x["cpu"])
        return procs[:limit]
    except ImportError:
        return []


def monitor_device(name: str, site: str = None) -> dict:
    """远程采集台账设备的资源状态（FDE 厂区模式）。

    从 site 台账按设备名解析连接, 经 SSH 远程采集 CPU/内存/负载。
    复用 remote.remote_monitor。设备不存在时明确报错。
    """
    from solo.factory.remote import remote_monitor, resolve_device
    r = resolve_device(name, site)
    if not r["ok"]:
        return r
    return remote_monitor(r["host"], r["user"], r["port"])


def monitor_devices(site: str = None) -> dict:
    """批量采集当前厂区所有设备的资源状态（FDE 巡检看板）。"""
    from solo.site import Site
    s = Site()
    site = site or s.current_site
    devices = s.devices(site)
    if not devices:
        return {"ok": False, "site": site, "error": "当前厂区无设备台账",
                "devices": []}
    results = []
    for d in devices:
        try:
            r = remote_monitor(d["host"], d.get("user", ""), d.get("port", 22))
            results.append({"name": d["name"], **r})
        except Exception as e:
            results.append({"name": d["name"], "ok": False, "error": str(e)})
    return {"ok": True, "site": site, "count": len(results), "devices": results}
