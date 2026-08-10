# -*- coding: utf-8 -*-
"""remote.py — 远程运维（对标 FDE 现场远程部署/排障）。

零依赖：调用系统 OpenSSH（Windows 10+ / Linux 自带）。
FDE 现场常连生产环境：SSH 连接测试 / 远程执行命令 / 远程部署。

安全：仅本地工具使用，主机/用户由用户配置，密码不入库。
"""
from __future__ import annotations

import shlex
import subprocess


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
    except subprocess.TimeoutExpired:
        return {"ok": False, "host": host, "error": "连接超时"}


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
    except subprocess.TimeoutExpired:
        return {"ok": False, "host": host, "command": command, "error": "执行超时"}


def remote_deploy(host: str, user: str = None, port: int = 22,
                  deploy_cmd: str = "cd /app && git pull && docker compose up -d") -> dict:
    """远程部署（FDE 现场部署生产环境，默认 git pull + 容器重启）。"""
    return run_command(host, deploy_cmd, user, port)


def remote_logs(host: str, user: str = None, port: int = 22,
                log_cmd: str = "docker compose logs --tail 100") -> dict:
    """远程查看日志（FDE 排障第一动作）。"""
    return run_command(host, log_cmd, user, port)


# ============================================================
# 设备名重载（FDE 厂区模式）：host 参数可传台账设备名，自动解析连接信息
# ============================================================

def resolve_device(name: str, site: str = None) -> dict:
    """按设备名从 site 台账解析连接信息。

    返回: {"ok": True, "host", "user", "port", "device"} 或 {"ok": False, "error"}。
    若 name 不在台账, 视为直接 host(向后兼容, 返回原样)。
    """
    from solo.site import Site
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


def device_connect(name: str, site: str = None) -> dict:
    """测试台账设备的 SSH 连接（FDE 厂区模式第一步）。"""
    r = resolve_device(name, site)
    if not r["ok"]:
        return r
    return test_connection(r["host"], r["user"], r["port"])


def remote_exec(host: str, command: str, user: str = None, port: int = 22) -> dict:
    """远程执行命令（host 可为台账设备名）。"""
    h, u, p, _ = _resolve_conn(host, user, port)
    return run_command(h, command, u, p)


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
