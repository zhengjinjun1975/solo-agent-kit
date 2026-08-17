# -*- coding: utf-8 -*-
"""ops.py — 现场运维能力面（site 台账 + SSH 远程 + 资源监控）。

合并 remote.py + monitor.py + site.py：三者同属「FDE 现场运维」概念域，
且 remote/monitor 都依赖 site（站点信息载体）。收敛为一个能力面，消除跨模块互引。

能力：
  - Site         厂区台账（role/current_site/devices，供监控/远程/工单定位）
  - SSH 远程     test_connection / run_command / remote_logs / remote_monitor
  - 资源监控      system_stats / monitor_devices（本机 + 厂区设备批量巡检）

零依赖：SSH 用系统 OpenSSH，采集用标准库（psutil 可选增强）。密码不入库。
"""
from __future__ import annotations

import os
import shlex
import subprocess


# ═══════════════════════════ 1. site：厂区台账（定位锚点）═══════════════════════════
DEFAULT_FILE = os.path.join(os.path.expanduser("~"), ".solo", "site.json")


class Site:
    """厂区配置：role / current_site / sites(含设备台账)。

    维护厂区上下文 + 设备台账（host/user/port），供监控/日志/远程/工单使用。
    密码不入库（仅 host/user/port），用系统 SSH key。
    """

    def __init__(self, file: str = DEFAULT_FILE):
        self.file = file
        os.makedirs(os.path.dirname(file), exist_ok=True)
        self._cfg = self._load()

    # ---- 读取 ----
    def _load(self) -> dict:
        if not os.path.exists(self.file):
            return {"role": "laptop", "current_site": "", "sites": {}}
        import json
        try:
            with open(self.file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"role": "laptop", "current_site": "", "sites": {}}

    # ---- 当前厂区（定位锚点）----
    @property
    def current_site(self) -> str:
        return self._cfg.get("current_site", "")

    def site_info(self, name: str = None) -> dict:
        """当前或指定厂区信息（含设备清单）。"""
        name = name or self.current_site
        return self._cfg.get("sites", {}).get(name, {})

    # ---- 设备台账 ----
    def devices(self, site: str = None) -> list:
        """当前/指定厂区的设备台账。"""
        info = self.site_info(site)
        return info.get("devices", []) if info else []

    def resolve_device(self, name: str, site: str = None) -> dict:
        """按设备名解析连接信息（供监控/远程用）。"""
        site = site or self.current_site
        for d in self.devices(site):
            if d["name"] == name:
                return {"ok": True, "device": d, "site": site}
        return {"ok": False, "error": f"当前厂区无设备: {name}", "site": site}

    # ---- 写入 ----
    def _save(self) -> None:
        """原子写回 site.json（临时文件 + os.replace，崩溃不损坏原配置）。"""
        import tempfile
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.file), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                import json
                json.dump(self._cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.file)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def add_device(self, name: str, site: str = None, host: str = None,
                   port: int = 22, user: str = None,
                   device_type: str = None, status: str = None,
                   power: str = None) -> dict:
        """往指定（或当前）厂区设备台账新增一台设备，写入 site.json。

        返回 {"ok": True, "device": ..., "site": ...} 或 {"ok": False, "error": ...}。
        厂区不存在时自动创建（以指定名或默认厂区）。
        """
        name = (name or "").strip()
        if not name:
            return {"ok": False, "error": "设备名必填"}
        site = (site or "").strip() or self.current_site or "默认厂区"
        sites = self._cfg.setdefault("sites", {})
        info = sites.setdefault(site, {"devices": []})
        devs = info.setdefault("devices", [])
        # 同厂区内设备名唯一
        for d in devs:
            if d.get("name") == name:
                return {"ok": False, "error": f"厂区「{site}」已存在设备 {name}"}
        device = {
            "name": name,
            "host": (host or "").strip() or "127.0.0.1",
            "port": int(port or 22),
            "user": (user or "").strip() or "root",
            "device_type": (device_type or "").strip(),
            "status": (status or "待机").strip() or "待机",
            "power": (power or "").strip(),
        }
        devs.append(device)
        if not self._cfg.get("current_site"):
            self._cfg["current_site"] = site
        self._save()
        return {"ok": True, "device": device, "site": site}


# ═══════════════════════════ 2. SSH 远程运维 ═══════════════════════════
def _ssh_base(host: str, user: str = None, port: int = 22) -> list:
    cmd = ["ssh"]
    if user:
        cmd += ["-l", user]
    if port != 22:
        cmd += ["-p", str(port)]
    cmd += ["-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes"]  # 非交互（无密码提示挂起）
    return cmd


def test_connection(host: str, user: str = None, port: int = 22) -> dict:
    """测试 SSH 连接（FDE 现场连生产环境第一步）。"""
    cmd = _ssh_base(host, user, port) + ["exit 0"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        ok = r.returncode == 0
        return {"ok": ok, "host": host, "user": user or "当前用户",
                "error": "" if ok else (r.stderr or r.stdout).strip()[:200]}
    except FileNotFoundError:
        # ssh 客户端缺失：环境断链 → 明确提示（需配置 SSH 目标/安装 OpenSSH 客户端）
        return {"ok": False, "host": host, "user": user or "当前用户",
                "error": "未检测到 ssh 命令：远程运维需配置 SSH 目标并安装 OpenSSH 客户端，"
                         "且已配置 SSH key（本机 ~/.ssh）。当前环境未满足，无法连接。"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "host": host, "error": "连接超时"}
    except OSError as e:
        return {"ok": False, "host": host, "user": user or "当前用户",
                "error": f"SSH 调用失败（需配置 SSH 目标）：{e}"}


def run_command(host: str, command: str, user: str = None, port: int = 22) -> dict:
    """远程执行命令（FDE 排障/部署）。"""
    if not command or not command.strip():
        return {"ok": False, "error": "命令为空"}
    cmd = _ssh_base(host, user, port) + [command]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return {"ok": r.returncode == 0, "host": host,
                "command": command, "exit_code": r.returncode,
                "stdout": (r.stdout or "")[-2000:],
                "stderr": (r.stderr or "")[-2000:]}
    except FileNotFoundError:
        # ssh 客户端缺失：环境断链 → 明确提示（需配置 SSH 目标/安装 OpenSSH 客户端）
        return {"ok": False, "host": host, "command": command,
                "error": "未检测到 ssh 命令：远程运维需配置 SSH 目标并安装 OpenSSH 客户端，"
                         "且已配置 SSH key（本机 ~/.ssh）。当前环境未满足，无法执行。"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "host": host, "command": command, "error": "执行超时"}
    except OSError as e:
        return {"ok": False, "host": host, "command": command,
                "error": f"SSH 调用失败（需配置 SSH 目标）：{e}"}


def remote_logs(host: str, user: str = None, port: int = 22,
                log_cmd: str = "docker compose logs --tail 100") -> dict:
    """远程查看日志（FDE 排障第一动作）。"""
    return run_command(host, log_cmd, user, port)


# ---- 设备名重载（FDE 厂区模式）：host 参数可传台账设备名，自动解析连接信息 ----
def resolve_device(name: str, site: str = None) -> dict:
    """按设备名从 site 台账解析连接信息。

    返回: {"ok": True, "host", "user", "port", "device"} 或 {"ok": False, "error"}。
    若 name 不在台账, 视为直接 host(向后兼容, 返回原样)。
    """
    s = Site()
    r = s.resolve_device(name, site)
    if not r["ok"]:
        return {"ok": False, "error": r["error"]}
    d = r["device"]
    return {"ok": True, "host": d["host"], "user": d.get("user", ""),
            "port": d.get("port", 22), "device": d.get("name", name)}


def _resolve_conn(host: str, user: str = None, port: int = 22):
    """解析 host 参数：若匹配台账设备名, 返回设备连接信息; 否则原样。

    返回 (host, user, port, device_name)。
    """
    try:
        r = resolve_device(host)
        if r["ok"]:
            return r["host"], r["user"] or user, r["port"], r["device"]
    except Exception:
        pass
    return host, user, port, host


def remote_monitor(host: str, user: str = None, port: int = 22) -> dict:
    """远程采集设备资源（CPU/内存/磁盘），host 可为台账设备名。

    远程执行 Linux 标准命令, 返回解析后的指标。零依赖(不装 agent)。
    """
    h, u, p, dev = _resolve_conn(host, user, port)
    cmd = (
        "echo '===CPU==='; top -bn1 | head -5 | tail -1; "
        "echo '===MEM==='; free -m | head -2; "
        "echo '===DISK==='; df -h / | tail -1; "
        "echo '===LOAD==='; cat /proc/loadavg"
    )
    r = run_command(h, cmd, u, p)
    if not r["ok"]:
        return {"ok": False, "device": dev, "host": h, "error": r.get("error") or r.get("stderr", "")}
    # 解析输出
    out = r.get("stdout", "")
    lines = out.splitlines()
    parsed = {"host": h, "device": dev, "raw": out[-1500:]}
    cpu_ln = next((ln for ln in lines if "%Cpu" in ln or "Cpu(s)" in ln), "")
    mem_ln = next((ln for ln in lines if "Mem:" in ln), "")
    disk_ln = next((ln for ln in lines if ln.strip().startswith("/") and "G" in ln), "")
    load_ln = next((ln for ln in lines if "load average" in ln), "")
    if not load_ln:
        # 备选: 无 "load average" 时, 匹配纯数字开头的 5 字段行
        load_ln = next((ln for ln in lines if ln.strip() and ln.strip()[0].isdigit() and len(ln.split()) == 5), "")
    if cpu_ln:
        import re
        m = re.search(r"([\d.]+)\s+id", cpu_ln)
        if m:
            parsed["cpu_percent"] = round(100 - float(m.group(1)), 1)
    if mem_ln:
        parts = mem_ln.split()
        if len(parts) >= 3:
            try:
                total, used = float(parts[1]), float(parts[2])
                parsed["mem_total_mb"] = int(total)
                parsed["mem_used_mb"] = int(used)
                parsed["mem_percent"] = round(used / total * 100, 1) if total else None
            except (ValueError, IndexError):
                pass
    if load_ln:
        parts = load_ln.split()
        nums = []
        try:
            if "load average" in load_ln:
                # 提取 "load average:" 之后的 3 个负载数字
                i = load_ln.find("load average")
                nums = [float(x) for x in load_ln[i+14:].split(",")[:3]]
            else:
                nums = [float(x) for x in parts[:3]]
            if len(nums) == 3:
                parsed["load1"], parsed["load5"], parsed["load15"] = nums
        except (ValueError, IndexError):
            pass
    return {"ok": True, **parsed}


# ═══════════════════════════ 3. 资源监控 ═══════════════════════════
def system_stats() -> dict:
    """采集本机系统资源状态（FDE 监控看板数据）。"""
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


def monitor_devices(site: str = None) -> dict:
    """批量采集当前厂区所有设备的资源状态（FDE 巡检看板）。"""
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
