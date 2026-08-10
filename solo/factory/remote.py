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
