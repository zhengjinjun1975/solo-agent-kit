# -*- coding: utf-8 -*-
"""netscan.py — 局域网设备扫描（纯 stdlib，零依赖）。

FDE 进厂区第一步：快速摸清局域网设备。
主机存活(ping) / 端口扫描(socket) / 服务识别(banner)。

零第三方依赖，符合套件原则。
"""
from __future__ import annotations

import socket
import subprocess
import re
from concurrent.futures import ThreadPoolExecutor

# 常见服务端口 banner 指纹
_SERVICES = {
    22: "SSH", 23: "Telnet", 21: "FTP", 80: "HTTP",
    443: "HTTPS", 502: "Modbus/TCP", 161: "SNMP", 3389: "RDP",
}


def scan_hosts(subnet: str, timeout: float = 1.0, workers: int = 64) -> list:
    """ping 存活探测。

    subnet: '192.168.1'（ping 192.168.1.1-254）
    timeout: ping 超时秒
    返回存活 IP 列表。
    """
    alive = []

    def _ping(ip: str) -> str | None:
        try:
            r = subprocess.run(
                ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip],
                capture_output=True, timeout=timeout + 1,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if r.returncode == 0:
                return ip
        except Exception:
            pass
        return None

    ips = [f"{subnet}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(_ping, ips):
            if res:
                alive.append(res)
    return sorted(alive, key=lambda x: int(x.rsplit(".", 1)[1]))


def scan_ports(host: str, ports: list = None, timeout: float = 1.0) -> list:
    """端口扫描（socket 连接测试）。返回开放端口列表。

    host: 目标 IP/域名
    ports: 要扫描的端口，None 用常见端口
    """
    if ports is None:
        ports = [21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 161, 443,
                 445, 502, 993, 995, 1433, 1521, 3306, 3389, 5432, 6379, 8080]
    open_ports = []

    def _test(port: int) -> int | None:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return port
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=50) as ex:
        for p in ex.map(_test, ports):
            if p:
                open_ports.append(p)
    return sorted(open_ports)


def detect_service(host: str, port: int, timeout: float = 1.0) -> dict:
    """服务识别（banner 抓取 + 端口指纹）。"""
    name = _SERVICES.get(port, "unknown")
    banner = ""
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            # 部分服务需要先发探测
            if port in (80, 443):
                s.sendall(b"HEAD / HTTP/1.0\r\n\r\n")
            elif port == 502:
                # Modbus 读保持寄存器请求
                s.sendall(bytes.fromhex("000100000006010300000001"))
            data = s.recv(64)
            banner = data.decode("utf-8", errors="ignore").strip()[:50]
            # Modbus 响应以 00 00 开头
            if port == 502 and data[:1] == b"\x00":
                name = "Modbus/TCP"
    except Exception:
        pass
    return {"port": port, "service": name, "banner": banner}
