# -*- coding: utf-8 -*-
"""netscan.py — 局域网设备扫描（纯 stdlib，零依赖）。

FDE 进厂区第一步：快速摸清局域网设备。
服务识别(banner)。零第三方依赖，符合套件原则。

（P2 清理：scan_hosts/scan_ports 死函数已删，保留 detect_service 服务识别）
"""
from __future__ import annotations

import socket

# 常见服务端口 banner 指纹
_SERVICES = {
    22: "SSH", 23: "Telnet", 21: "FTP", 80: "HTTP",
    443: "HTTPS", 502: "Modbus/TCP", 161: "SNMP", 3389: "RDP",
}


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
