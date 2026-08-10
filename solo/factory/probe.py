# -*- coding: utf-8 -*-
"""probe.py — 工业协议探针（纯 stdlib，零依赖）。

FDE 现场对接厂区设备：Modbus/TCP、HTTP、SNMPv1 服务探测。
Modbus TCP 用纯 socket 手写协议（MBAP 头 + 功能码 0x03 读保持寄存器），
不引 pymodbus，保持套件零第三方依赖。

能力：
  ProtocolProbe.modbus_read   读保持寄存器(FC 0x03)
  ProtocolProbe.http_status   HTTP 服务状态
  ProtocolProbe.snmp_probe    SNMPv1 GET sysDescr
  ProtocolProbe.discover      常见工业/IT服务端口发现
  detect_device               模块级一键探测
"""
from __future__ import annotations

import socket
import struct
import urllib.request

# 常见工业/IT 服务端口
COMMON_PORTS = {21: "FTP", 22: "SSH", 23: "Telnet", 80: "HTTP",
                161: "SNMP", 443: "HTTPS", 502: "Modbus/TCP", 3389: "RDP"}


class ProtocolProbe:
    """工业协议多源探针，纯 stdlib 实现（socket/urllib）。"""

    def __init__(self, host: str, port: int, timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    # ── Modbus/TCP (功能码 0x03 读保持寄存器) ─────────────
    def modbus_read(self, unit: int = 1, address: int = 0, count: int = 1) -> list:
        """Modbus TCP Read Holding Registers (FC 0x03)。

        请求：MBAP头(事务ID2+协议ID2+长度2+单元ID1) + 功能码0x03 + 起始地址2 + 数量2
        响应：MBAP头 + 功能码 + 字节数 + 寄存器值(每寄存器2字节, 大端)
        返回寄存器值的无符号整数列表。连接/解析失败返回空列表。
        """
        try:
            # 构造请求 PDU: 功能码(1) + 起始地址(2) + 数量(2) = 5字节
            pdu = struct.pack(">BHH", 0x03, address, count)
            txid = 1
            # MBAP 头: 事务ID(2) + 协议ID(2,=0) + 长度(2) + 单元ID(1)
            mbap = struct.pack(">HHHB", txid, 0, 1 + len(pdu), unit)
            req = mbap + pdu

            with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
                s.settimeout(self.timeout)
                s.sendall(req)
                resp = s.recv(512)
            if len(resp) < 10:
                return []
            # 校验功能码（第7字节应为0x03）
            if resp[7] != 0x03:
                return []
            byte_count = resp[8]
            vals = []
            for i in range(byte_count // 2):
                vals.append(struct.unpack(">H", resp[9 + i * 2: 11 + i * 2])[0])
            return vals
        except Exception:
            return []

    # ── HTTP 服务状态 ─────────────
    def http_status(self, path: str = "/") -> dict:
        """HTTP 请求，返回 {status, reason, server}。失败返回空 dict。"""
        try:
            url = f"http://{self.host}:{self.port}{path}"
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return {"status": r.status, "reason": r.reason,
                        "server": r.headers.get("Server", "")}
        except urllib.error.HTTPError as e:
            return {"status": e.code, "reason": e.reason,
                    "server": e.headers.get("Server", "") if e.headers else ""}
        except Exception:
            return {}

    # ── SNMPv1 GET (sysDescr) ─────────────
    def snmp_probe(self, community: str = "public") -> dict:
        """SNMPv1 GET sysDescr(1.3.6.1.2.1.1.1.0)。返回 {'ok', 'sys_descr'}。"""
        try:
            # 手工构造 SNMPv1 GET 请求（BER 编码，只覆盖 sysDescr 简单场景）
            oid = b"\x2b\x06\x01\x02\x01\x01\x01\x00"  # 1.3.6.1.2.1.1.1.0
            comm = community.encode()
            # 简化 BER: version(0) + community + PDU
            varbind = b"\x30" + bytes([len(oid) + 4]) + b"\x06" + bytes([len(oid)]) + oid + b"\x05\x00"
            varbind_list = b"\x30" + bytes([len(varbind)]) + varbind
            pdu = b"\xa0" + bytes([len(varbind_list)]) + b"\x02\x01\x01" + b"\x02\x01\x00" + varbind_list
            msg = b"\x30" + bytes([2 + len(comm) + len(pdu)]) + b"\x02\x01\x00" + \
                  bytes([len(comm)]) + comm + pdu

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            sock.sendto(msg, (self.host, self.port))
            data, _ = sock.recvfrom(2048)
            sock.close()
            # 简单解析：查找 sysDescr 响应中的字符串值（近似，仅检测可达性）
            return {"ok": len(data) > 0, "sys_descr": data[-40:].decode("utf-8", errors="ignore").strip()}
        except Exception:
            return {"ok": False, "sys_descr": ""}

    # ── 服务发现 ─────────────
    def discover(self, ports: dict = None) -> list:
        """探测常见服务端口，返回开放服务列表 [{port, service}]。"""
        ports = ports or COMMON_PORTS
        found = []
        for port, svc in ports.items():
            try:
                with socket.create_connection((self.host, port), timeout=self.timeout):
                    found.append({"port": port, "service": svc})
            except Exception:
                pass
        return found


def detect_device(host: str, ports: dict = None) -> dict:
    """模块级一键探测：服务发现 + Modbus + HTTP 状态。"""
    p = ProtocolProbe(host, 502, timeout=1.5)
    services = p.discover(ports)
    result = {"host": host, "services": services, "modbus": False, "http": False}
    if any(s["port"] == 502 for s in services):
        regs = ProtocolProbe(host, 502, timeout=1.5).modbus_read()
        result["modbus"] = len(regs) > 0
    if any(s["port"] in (80, 443) for s in services):
        hp = ProtocolProbe(host, 80 if any(s["port"] == 80 for s in services) else 443, timeout=1.5)
        result["http"] = bool(hp.http_status())
    return result
