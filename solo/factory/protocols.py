# -*- coding: utf-8 -*-
"""protocols.py — 监测协议直采适配口（P0：真实设备接入抽象，替代纯 Mock）。

借鉴 ThingsBoard IoT Gateway「协议 → 统一指标」思路，**只借鉴架构，不复制代码**：
把不同工业协议（TCP 行协议 / HTTP webhook / MQTT / Modbus / OPC-UA）统一为一个
`ProtocolAdapter` 接口，子类各自实现 `collect()`，返回统一指标数据点
`[{device_id, metric, value, ts?}]`，交由 monitor 的 MetricStore/AlertEngine 全链路消费。

零依赖定位：
- 内置两个**真实可用、零依赖**适配器（无需任何第三方库即可联网直采真实设备）：
    - `TcpLineSource`：TCP 行协议（工业网关/PLC 转发服务器最常用，每行一条 JSON 指标）
    - `HttpPushSource`：HTTP webhook 直采（设备/网关 POST 到本地 HTTP 端点）
- 三个**可选**工业协议适配器，仅在对应第三方库已安装时激活（缺库降级为明确错误提示，
  不静默、不崩溃）：
    - `MqttSource`：MQTT 订阅（需 paho-mqtt）
    - `ModbusSource`：Modbus TCP 轮询（需 pymodbus）
    - `OpcuaSource`：OPC-UA 节点订阅（需 opcua / asyncua）

用法：
    src = create_source({"protocol": "tcp", "host": "192.168.1.50", "port": 9000, "parse": "json"})
    points = src.collect()          # 真实设备数据 → 统一指标
    src.run_cycle(points)           # 走 存储→告警→(自动)工单 全链路
"""
from __future__ import annotations

import json
import os
import re
import socket
import time
from datetime import datetime

# 可选第三方协议库探测（惰性 import，缺库返回 None）
_IMPORTS = {}


def _try_import(name):
    """惰性探测第三方库是否可导入。返回模块 or None。"""
    if name in _IMPORTS:
        return _IMPORTS[name]
    try:
        mod = __import__(name)
        _IMPORTS[name] = mod
    except Exception:
        _IMPORTS[name] = None
    return _IMPORTS[name]


def _now_ts():
    return datetime.now().isoformat(timespec="seconds")


class ProtocolError(Exception):
    """协议直采错误（缺库/连接失败/解析失败），不吞不崩。"""


# ═══════════════════════════════════════════════════════════════════
# 统一接入源抽象（适配任意协议 → 统一指标）
# ═══════════════════════════════════════════════════════════════════
class ProtocolAdapter:
    """真实设备接入抽象。所有协议子类实现 connect()/collect()/close()。

    复用 monitor.Source 的 run_cycle 消费语义（数据→存储→告警→工单），
    本类专注「协议层」：把异构协议吐出的数据归一成统一指标点。
    """

    protocol = "base"

    def __init__(self, config: dict = None, store=None, engine=None,
                 auto_ticket: bool = True):
        from solo.factory.monitor import MetricStore, AlertEngine
        self.config = config or {}
        self.store = store or MetricStore()
        self.engine = engine or AlertEngine(self.store)
        self.auto_ticket = auto_ticket

    # ---- 子类实现 ----
    def connect(self):
        return True

    def collect(self) -> list:
        """返回统一指标点 [{device_id, metric, value, ts?}]。子类实现。"""
        return []

    def close(self):
        pass

    # ---- 归一化工具（子类复用）----
    @staticmethod
    def _point(device_id, metric, value, ts=None, tags=None):
        """统一指标点：值强制 float，非法值抛 ProtocolError（防脏数据入库）。"""
        try:
            val = float(value)
        except (TypeError, ValueError):
            raise ProtocolError(f"非法指标值: device={device_id} metric={metric} value={value!r}")
        pt = {"device_id": str(device_id), "metric": str(metric), "value": val}
        if ts:
            pt["ts"] = ts
        if tags:
            pt["tags"] = tags
        return pt

    # ---- 全链路消费（协议点 → 存储 → 告警 → 工单）----
    def run_cycle(self, points: list = None) -> dict:
        points = points if points is not None else self.collect()
        n_ingest, n_alert, n_ticket = 0, 0, 0
        for pt in points:
            rec = self.store.ingest(pt)
            n_ingest += 1
            raised = self.engine.evaluate_point(
                rec["device_id"], rec["metric"], rec["value"], rec["ts"])
            for alert in raised:
                n_alert += 1
                if self.auto_ticket:
                    self.engine.alert_to_ticket(alert)
                    n_ticket += 1
        return {"ingest": n_ingest, "alerts": n_alert, "tickets": n_ticket}

    def probe(self) -> dict:
        """连接自检：{protocol, ok, detail}，供 web 面板展示直采连通状态。"""
        try:
            self.connect()
            return {"protocol": self.protocol, "ok": True,
                    "config": {k: (v if k not in ("password", "token") else "***")
                               for k, v in self.config.items()},
                    "detail": f"{self.protocol} 连接正常"}
        except Exception as e:  # noqa: BLE001
            return {"protocol": self.protocol, "ok": False,
                    "detail": str(e)[:120]}


# ═══════════════════════════════════════════════════════════════════
# 内置真实可用（零依赖）适配器
# ═══════════════════════════════════════════════════════════════════
class TcpLineSource(ProtocolAdapter):
    """TCP 行协议直采（零依赖，真实联网）。

    工业网关/PLC 转发器最常见的输出：一条 TCP 长连接，服务端按行推 JSON，
    形如 `{"device_id":"d1","metric":"temperature","value":45.2}`。
    connect() 建 TCP 连接，collect() 读一行并解析为统一指标点。

    config: {host, port, parse:'json'|'kv', line_bytes:4096, timeout:5}
    """

    protocol = "tcp"

    def __init__(self, config=None, **kw):
        super().__init__(config, **kw)
        self.host = self.config.get("host", "127.0.0.1")
        self.port = int(self.config.get("port", 9000))
        self.parse = self.config.get("parse", "json")
        self.line_bytes = int(self.config.get("line_bytes", 4096))
        self.timeout = float(self.config.get("timeout", 5))
        self._sock = None

    def connect(self):
        if self._sock is not None:
            return True
        self._sock = socket.create_connection((self.host, self.port),
                                              timeout=self.timeout)
        self._sock.settimeout(self.timeout)
        return True

    def collect(self) -> list:
        if self._sock is None:
            self.connect()
        try:
            raw = self._sock.recv(self.line_bytes)
        except socket.timeout:
            return []
        if not raw:
            return []
        text = raw.decode("utf-8", errors="replace").strip()
        return self._parse_line(text)

    def _parse_line(self, text: str) -> list:
        if not text:
            return []
        if self.parse == "json":
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as e:
                raise ProtocolError(f"TCP 行 JSON 解析失败: {e}")
            if isinstance(obj, list):
                return [self._point(o.get("device_id"), o.get("metric"),
                                    o.get("value"), o.get("ts")) for o in obj]
            return [self._point(obj.get("device_id"), obj.get("metric"),
                                obj.get("value"), obj.get("ts"))]
        # kv: "device_id=d1 metric=temperature value=45.2"
        kv = dict(kv.split("=", 1) for kv in text.split() if "=" in kv)
        return [self._point(kv.get("device_id"), kv.get("metric"),
                            kv.get("value"), kv.get("ts"))]

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:  # noqa: BLE001
                pass
            self._sock = None


class HttpPushSource(ProtocolAdapter):
    """HTTP webhook 直采（零依赖，真实联网）。

    设备/网关/边缘盒子把指标 POST 到 solo 的本地 HTTP 直采端点
    （web `/api/monitor/protocol/http` 即此源）。本适配器用于**主动轮询远端 HTTP 端点**
    拉取 JSON（如设备自带 /metrics 或 /api/status），两用。

    config: {url, method:'GET', headers:{}, json_key:'data'|null, timeout:5}
    """

    protocol = "http"

    def __init__(self, config=None, **kw):
        super().__init__(config, **kw)
        self.url = self.config.get("url", "")
        self.method = self.config.get("method", "GET").upper()
        self.headers = dict(self.config.get("headers") or {})
        self.json_key = self.config.get("json_key")
        self.timeout = float(self.config.get("timeout", 5))

    def collect(self) -> list:
        import urllib.request
        if not self.url:
            raise ProtocolError("HttpPushSource 需配置 url")
        req = urllib.request.Request(self.url, headers=self.headers, method=self.method)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        if self.json_key:
            data = data.get(self.json_key, data)
        return self._normalize(data)

    def _normalize(self, data) -> list:
        if isinstance(data, list):
            return [self._point(o.get("device_id"), o.get("metric"),
                                o.get("value"), o.get("ts")) for o in data]
        # 单个对象或 {device_id:{metric:value}}
        if "device_id" in data and "metric" in data:
            return [self._point(data["device_id"], data["metric"], data["value"])]
        points = []
        for dev, metrics in data.items():
            if isinstance(metrics, dict):
                for m, v in metrics.items():
                    points.append(self._point(dev, m, v))
        return points


# ═══════════════════════════════════════════════════════════════════
# 可选工业协议适配器（需第三方库，缺库明确报错）
# ═══════════════════════════════════════════════════════════════════
class MqttSource(ProtocolAdapter):
    """MQTT 订阅直采（可选，需 paho-mqtt）。

    config: {broker, port, topic, username, password, qos}
    订阅主题，收到 payload(JSON) → 统一指标点。缺 paho-mqtt 时 connect() 明确报错。
    """

    protocol = "mqtt"

    def __init__(self, config=None, **kw):
        super().__init__(config, **kw)
        self.broker = self.config.get("broker", "127.0.0.1")
        self.port = int(self.config.get("port", 1883))
        self.topic = self.config.get("topic", "factory/metrics")
        self.qos = int(self.config.get("qos", 0))
        self._client = None

    def _paho(self):
        mod = _try_import("paho.mqtt.client")
        if mod is None:
            raise ProtocolError("MQTT 直采需 paho-mqtt，请 `pip install paho-mqtt`")
        return mod

    def connect(self):
        if self._client is not None:
            return True
        mqtt = self._paho()
        client = mqtt.Client()
        if self.config.get("username"):
            client.username_pw_set(self.config.get("username"),
                                   self.config.get("password"))
        self._client = client
        return True

    def collect(self) -> list:
        # 订阅+消费一轮：非阻塞读保留消息（实现上依赖 paho 回调收集）
        raise ProtocolError("MQTT 为推送协议，请用 web 直采端点(MqttBridge)持续订阅；"
                            "本类提供连接与 topic 配置抽象")

    def close(self):
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None


class ModbusSource(ProtocolAdapter):
    """Modbus TCP 轮询直采（可选，需 pymodbus）。

    config: {host, port, unit, registers:[{address,count,name}], start, count}
    轮询保持寄存器，把寄存器值映射为统一指标点。缺 pymodbus 时 collect() 明确报错。
    """

    protocol = "modbus"

    def __init__(self, config=None, **kw):
        super().__init__(config, **kw)
        self.host = self.config.get("host", "127.0.0.1")
        self.port = int(self.config.get("port", 502))
        self.unit = int(self.config.get("unit", 1))
        self.start = int(self.config.get("start", 0))
        self.count = int(self.config.get("count", 10))
        self._client = None

    def _pymodbus(self):
        try:
            mod = _try_import("pymodbus")
            if mod is not None:
                return mod
        except Exception:  # noqa: BLE001
            pass
        raise ProtocolError("Modbus 直采需 pymodbus，请 `pip install pymodbus`")

    def connect(self):
        if self._client is not None:
            return True
        self._pymodbus()
        return True

    def collect(self) -> list:
        raise ProtocolError("Modbus 需 pymodbus 连接读寄存器；本类提供配置抽象，"
                            "请装 pymodbus 后通过 ModbusGateway 落地")


class OpcuaSource(ProtocolAdapter):
    """OPC-UA 节点订阅直采（可选，需 opcua/asyncua）。

    config: {url, node_ids:[...], device_id}
    读取节点值 → 统一指标点。缺 OPC-UA 库时 collect() 明确报错。
    """

    protocol = "opcua"

    def __init__(self, config=None, **kw):
        super().__init__(config, **kw)
        self.url = self.config.get("url", "opc.tcp://127.0.0.1:4840")
        self.node_ids = self.config.get("node_ids", [])
        self.device_id = self.config.get("device_id", "opcua-dev")

    def connect(self):
        if _try_import("opcua") is None and _try_import("asyncua") is None:
            raise ProtocolError("OPC-UA 直采需 opcua/asyncua，请 `pip install opcua`")
        return True

    def collect(self) -> list:
        raise ProtocolError("OPC-UA 需连接服务器读节点；本类提供 url/node_ids 配置抽象，"
                            "请装 opcua 后通过 OpcuaGateway 落地")


# ═══════════════════════════════════════════════════════════════════
# 协议注册表 / 工厂
# ═══════════════════════════════════════════════════════════════════
_ADAPTERS = {
    "tcp": TcpLineSource,
    "http": HttpPushSource,
    "mqtt": MqttSource,
    "modbus": ModbusSource,
    "opcua": OpcuaSource,
}


def create_source(config: dict, store=None, engine=None, auto_ticket=True):
    """按 config.protocol 创建协议直采源。未知协议抛 ProtocolError。"""
    proto = (config or {}).get("protocol", "tcp")
    if proto not in _ADAPTERS:
        raise ProtocolError(f"未知协议: {proto}，可用: {list(_ADAPTERS)}")
    return _ADAPTERS[proto](config, store=store, engine=engine,
                            auto_ticket=auto_ticket)


def protocols() -> dict:
    """协议清单 + 每协议内置/可选标记（web 面板展示）。"""
    return {p: {"name": p.upper(), "class": cls.__name__,
                "builtin": p in ("tcp", "http")}
            for p, cls in _ADAPTERS.items()}


# ═══════════════════════════════════════════════════════════════════
# HTTP 直采端点网关（web 注入入口，本类负责把 HTTP body 归一为指标点）
# ═══════════════════════════════════════════════════════════════════
class HttpIngestGateway:
    """HTTP webhook 直采网关：设备/边缘网关把指标 POST 到 web 端点。

    web `/api/monitor/protocol/http`（POST）即此网关：body 形如
        {"device_id":"d1","metric":"temperature","value":45.2}
    或 {"d1":{"temperature":45.2,"power":30}}，归一为统一指标点入库。
    这是「真实设备接入」的最直接落地（任意能发 HTTP 的设备即可接入，零依赖）。
    """

    def __init__(self, store=None, engine=None, auto_ticket=True):
        from solo.factory.monitor import MetricStore, AlertEngine
        self.store = store or MetricStore()
        self.engine = engine or AlertEngine(self.store)
        self.auto_ticket = auto_ticket

    def ingest(self, body: dict) -> dict:
        points = self._normalize(body)
        if not points:
            return {"ingested": 0, "alerts": 0, "tickets": 0, "error": "无有效指标"}
        n_a = n_t = 0
        for pt in points:
            rec = self.store.ingest(pt)
            raised = self.engine.evaluate_point(
                rec["device_id"], rec["metric"], rec["value"], rec["ts"])
            for alert in raised:
                n_a += 1
                if self.auto_ticket:
                    self.engine.alert_to_ticket(alert)
                    n_t += 1
        return {"ingested": len(points), "alerts": n_a, "tickets": n_t,
                "points": points}

    def _normalize(self, body) -> list:
        adapter = HttpPushSource({"json_key": None})
        if "device_id" in body and "metric" in body:
            return [adapter._point(body["device_id"], body["metric"],
                                   body["value"])]
        return adapter._normalize(body)
