# -*- coding: utf-8 -*-
"""_impl/device.py — monitor-device 有状态实现（MetricStore + AlertEngine + protocols）。

状态与 IO 在原子内；统计/判则纯函数来自 kernels.monitor_stats 与 kernels.forecast。
"""
from __future__ import annotations

import json
import os


class MetricStore:
    """指标存储：增量写 JSON + 系列查询 + 规则 + 告警。"""

    def __init__(self, dir):
        self.dir = dir or os.path.join(os.path.expanduser("~"), ".solo", "monitor")
        os.makedirs(self.dir, exist_ok=True)
        self._series_path = os.path.join(self.dir, "series.json")
        self._rules_path = os.path.join(self.dir, "rules.json")
        self._alerts_path = os.path.join(self.dir, "alerts.json")

    def _load(self, path, default):
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return default
        return default

    def _save(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def ingest(self, points):
        """points: list[dict] 或 dict。返回 {ingested:[...], count}。"""
        if isinstance(points, dict):
            points = [points]
        series = self._load(self._series_path, [])
        recs = []
        for p in points:
            rec = {"device_id": p.get("device_id"), "metric": p.get("metric"),
                   "value": p.get("value"), "ts": p.get("ts", "")}
            series.append(rec)
            recs.append(rec)
        self._save(self._series_path, series)
        return {"ingested": recs, "count": len(recs)}

    def series(self, device_id=None, metric=None):
        series = self._load(self._series_path, [])
        out = series
        if device_id:
            out = [s for s in out if s.get("device_id") == device_id]
        if metric:
            out = [s for s in out if s.get("metric") == metric]
        return out

    def values(self, device_id=None, metric=None):
        """提取数值序列（供 SPC/阈值）。"""
        return [s.get("value") for s in self.series(device_id, metric)
                if isinstance(s.get("value"), (int, float))]

    def set_rule(self, device_id, metric, cmp_op, threshold, level="warn", enabled=True):
        rules = self._load(self._rules_path, [])
        for r in rules:
            if r.get("device_id") == device_id and r.get("metric") == metric:
                r.update({"cmp_op": cmp_op, "threshold": threshold,
                          "level": level, "enabled": enabled})
                self._save(self._rules_path, rules)
                return r
        rule = {"device_id": device_id, "metric": metric, "cmp_op": cmp_op,
                "threshold": threshold, "level": level, "enabled": enabled}
        rules.append(rule)
        self._save(self._rules_path, rules)
        return rule

    def rules(self, device_id=None):
        rules = self._load(self._rules_path, [])
        if device_id:
            rules = [r for r in rules if r.get("device_id") == device_id]
        return rules

    def add_alert(self, device_id, metric, value, level, message, ts):
        alerts = self._load(self._alerts_path, [])
        alerts.append({"device_id": device_id, "metric": metric, "value": value,
                       "level": level, "message": message, "ts": ts})
        self._save(self._alerts_path, alerts)
        return alerts

    def alerts(self, device_id=None, limit=50):
        alerts = self._load(self._alerts_path, [])
        if device_id:
            alerts = [a for a in alerts if a.get("device_id") == device_id]
        return alerts[-int(limit):]


class AlertEngine:
    """阈值告警引擎：对照规则判则，越限生成告警。"""

    def __init__(self, store):
        self.store = store

    def evaluate(self, device_id, metric, value, ts=""):
        from kernels.monitor_stats import match_condition
        alerts = []
        for rule in self.store.rules(device_id):
            if rule.get("metric") != metric or not rule.get("enabled", True):
                continue
            if match_condition(value, rule.get("cmp_op", ">"), rule.get("threshold", 0)):
                msg = f"{device_id} {metric}={value} {rule.get('cmp_op')} 阈值{rule.get('threshold')}"
                alerts.append({"device_id": device_id, "metric": metric, "value": value,
                               "level": rule.get("level", "warn"), "message": msg, "ts": ts})
                self.store.add_alert(device_id, metric, value, rule.get("level", "warn"), msg, ts)
        return alerts


class RuleChain:
    """规则链：多条件组合规则（AND 语义）。"""

    def __init__(self, store):
        self.store = store
        self._chain_path = os.path.join(store.dir, "chain.json")

    def _load(self):
        if os.path.exists(self._chain_path):
            try:
                with open(self._chain_path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def add(self, rule):
        rules = self._load()
        rules.append(rule)
        with open(self._chain_path, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        return rule

    def list(self):
        return self._load()


# ---- 协议适配器（缺库降级）----
class ProtocolAdapter:
    def __init__(self, kind, config=None):
        self.kind = kind
        self.config = config or {}

    def available(self):
        if self.kind == "tcp":
            return True
        if self.kind in ("mqtt",):
            try:
                import paho.mqtt  # noqa: F401
                return True
            except ImportError:
                return False
        if self.kind in ("modbus",):
            try:
                import pymodbus  # noqa: F401
                return True
            except ImportError:
                return False
        if self.kind in ("opcua",):
            try:
                import opcua  # noqa: F401
                return True
            except ImportError:
                return False
        if self.kind in ("http", "csv"):
            return True
        return False
