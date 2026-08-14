# -*- coding: utf-8 -*-
"""monitor.py — 设备数据监测 P0（借鉴 DataBuff「指标采集→存储→告警→AI问数」骨架）。

DataBuff 是 AGPL 开源 APM，本模块仅**借鉴其设计思路**（统一时序存储 + 定时告警评估
+ 事件记录 + 恢复自动关闭 + 自然语言问数），用工厂设备场景 + 用户生态自研，零依赖、
纯标准库，**不引入 DataBuff 代码**（规避 AGPL 传染）。

数据流（DataBuff 同构骨架）：
    接入源(Source) → 统一指标存储(MetricStore, device_metric 时序)
        → 告警评估引擎(AlertEngine: 阈值 + 突变检测 + 恢复自动关闭)
        → 工单状态机(open → in_progress → done) + AI问数(MonitorAsk)

零依赖：MQTT 用抽象 Source 接口；真实 MQTT 需 paho-mqtt（可选），缺省用 Mock 源模拟。
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta

DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".solo", "monitor")


def _now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_ts(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.min


def _atomic_write(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ═══════════════════════════════════════════════════════════════════════
# 1. 统一指标存储 MetricStore（device_metric 时序模型）
# ═══════════════════════════════════════════════════════════════════════
class MetricStore:
    """统一指标存储：设备指标时间序列。

    记录模型 device_metric = {device_id, metric, value, ts, tags}，JSON 持久化。
    借鉴 DataBuff「Doris 统一时序存储 + 分钟级预聚合」思路，提供：
      record / series / latest / window / aggregate(分钟预聚合) / recent_alerts
    """

    def __init__(self, dir: str = DEFAULT_DIR):
        self.dir = dir
        os.makedirs(dir, exist_ok=True)
        self.metrics_file = os.path.join(dir, "metrics.json")
        self.alerts_file = os.path.join(dir, "alerts.json")
        self.rules_file = os.path.join(dir, "rules.json")
        self.tickets_file = os.path.join(dir, "tickets.json")
        self._metrics = self._load(self.metrics_file, [])
        self._alerts = self._load(self.alerts_file, [])
        self._rules = self._load(self.rules_file, [])
        self._tickets = self._load(self.tickets_file, [])

    # ---- 加载/持久化 ----
    def _load(self, path: str, default):
        if not os.path.exists(path):
            return default
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save(self, attr: str, file_attr: str, data) -> None:
        setattr(self, attr, data)
        _atomic_write(getattr(self, file_attr), data)

    # ---- 记录指标 ----
    def record(self, device_id: str, metric: str, value: float,
               ts: str = None, tags: dict = None) -> dict:
        """写入一条设备指标。返回记录。"""
        rec = {"device_id": device_id, "metric": metric,
               "value": float(value),
               "ts": ts or _now_ts(),
               "tags": tags or {}}
        self._metrics.append(rec)
        self._save("_metrics", "metrics_file", self._metrics)
        return rec

    def ingest(self, payload: dict) -> dict:
        """统一接入入口：{device_id, metric, value, ts?, tags?} 或 list[dict]。"""
        if isinstance(payload, list):
            return [self.ingest(p) for p in payload][-1] if payload else {}
        rec = self.record(payload.get("device_id"), payload.get("metric"),
                          payload.get("value"), payload.get("ts"),
                          payload.get("tags"))
        return rec

    # ---- 查询 ----
    def series(self, device_id: str = None, metric: str = None) -> list:
        """按设备/指标过滤时序（默认全部，按时间升序）。"""
        out = [r for r in self._metrics
               if (device_id is None or r["device_id"] == device_id)
               and (metric is None or r["metric"] == metric)]
        return sorted(out, key=lambda r: _parse_ts(r["ts"]))

    def latest(self, device_id: str = None, metric: str = None):
        """最新一条（None 若无）。"""
        s = self.series(device_id, metric)
        return s[-1] if s else None

    def window(self, device_id: str, metric: str, minutes: int = 5) -> list:
        """近 N 分钟窗口数据（突变检测/恢复评估用）。"""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [r for r in self.series(device_id, metric)
                if _parse_ts(r["ts"]) >= cutoff]

    def aggregate(self, device_id: str = None, metric: str = None,
                  minutes: int = 1) -> list:
        """分钟级预聚合（借鉴 DataBuff 分钟聚合）：按分钟桶取均值。

        返回 [{bucket, device_id, metric, avg, min, max, count}]。
        """
        series = self.series(device_id, metric)
        buckets = {}
        for r in series:
            ts = _parse_ts(r["ts"]).replace(second=0, microsecond=0)
            key = (ts.isoformat(timespec="minutes"), r["device_id"], r["metric"])
            b = buckets.setdefault(key, {"bucket": key[0], "device_id": key[1],
                                         "metric": key[2], "sum": 0.0,
                                         "min": r["value"], "max": r["value"],
                                         "count": 0})
            b["sum"] += r["value"]
            b["min"] = min(b["min"], r["value"])
            b["max"] = max(b["max"], r["value"])
            b["count"] += 1
        out = []
        for b in buckets.values():
            out.append({"bucket": b["bucket"], "device_id": b["device_id"],
                        "metric": b["metric"], "avg": round(b["sum"] / b["count"], 2),
                        "min": b["min"], "max": b["max"], "count": b["count"]})
        return sorted(out, key=lambda x: x["bucket"])

    def devices(self) -> list:
        """去重设备清单。"""
        seen, out = set(), []
        for r in self._metrics:
            if r["device_id"] not in seen:
                seen.add(r["device_id"])
                out.append(r["device_id"])
        return out

    # ---- 告警规则 ----
    def set_rule(self, device_id: str, metric: str, op: str, threshold: float,
                 level: str = "medium", mutate_pct: float = None,
                 label: str = None) -> dict:
        """设置告警规则。

        op: '>' 或 '<' 阈值触发。
        mutate_pct: 突变检测阈值（环比窗口均值变化百分比，None=不启用突变检测）。
        """
        rule = {"device_id": device_id, "metric": metric, "op": op,
                "threshold": float(threshold), "level": level,
                "mutate_pct": mutate_pct,
                "label": label or f"{device_id}.{metric}"}
        self._rules = [r for r in self._rules
                       if not (r["device_id"] == device_id and r["metric"] == metric)]
        self._rules.append(rule)
        self._save("_rules", "rules_file", self._rules)
        return rule

    def rules(self, device_id: str = None) -> list:
        if device_id is None:
            return self._rules
        return [r for r in self._rules if r["device_id"] == device_id]

    def clear_rules(self) -> None:
        self._save("_rules", "rules_file", [])

    # ---- 告警记录 ----
    def alerts(self, state: str = None, device_id: str = None, limit: int = 50) -> list:
        out = self._alerts
        if state:
            out = [a for a in out if a["state"] == state]
        if device_id:
            out = [a for a in out if a["device_id"] == device_id]
        out = sorted(out, key=lambda a: a.get("raised_at", ""), reverse=True)
        return out[:limit]

    # ---- 工单记录（状态机 open→in_progress→done）----
    def tickets(self, state: str = None) -> list:
        out = self._tickets
        if state:
            out = [t for t in out if t["state"] == state]
        return sorted(out, key=lambda t: t.get("ts", ""), reverse=True)


# ═══════════════════════════════════════════════════════════════════════
# 2. 告警评估引擎 AlertEngine（阈值 + 突变检测 + 恢复自动关闭）
# ═══════════════════════════════════════════════════════════════════════
class AlertEngine:
    """告警评估引擎。

    借鉴 DataBuff 告警链路「规则配置 → 定时评估 → 事件记录（触发/恢复/状态）」：
      - 阈值告警：metric 最新值 op threshold → 触发
      - 突变检测：环比近窗口均值变化率超过 mutate_pct → 触发（异常跳变，如温度骤升）
      - 恢复自动关闭：指标回到阈值内 / 突变回稳 → 自动标记 recovered 并关闭工单
    告警记录 = {id, device_id, metric, type(threshold/mutate), value, op, threshold,
               level, state(firing/recovered), raised_at, recovered_at, events[]}。
    """

    def __init__(self, store: MetricStore = None):
        self.store = store or MetricStore()

    # ---- 单点评估（核心）----
    def evaluate_point(self, device_id: str, metric: str, value: float,
                       ts: str = None) -> list:
        """对一条新指标评估其规则，返回本次触发的告警列表（含自动恢复关闭）。"""
        rules = [r for r in self.store.rules(device_id)
                 if r["metric"] == metric]
        raised = []
        for rule in rules:
            trig = False
            a_type = None
            # 1) 阈值告警
            val = float(value)
            if rule["op"] == ">" and val > rule["threshold"]:
                trig, a_type = True, "threshold"
            elif rule["op"] == "<" and val < rule["threshold"]:
                trig, a_type = True, "threshold"
            # 2) 突变检测（窗口均值环比变化率）
            if not trig and rule.get("mutate_pct") is not None:
                mv = self._mutate(device_id, metric, value, rule["mutate_pct"])
                if mv is not None and mv["detected"]:
                    trig, a_type = True, "mutate"
            self._evaluate_rule(device_id, metric, value, rule, trig, a_type, ts, raised)
        return raised

    def _mutate(self, device_id: str, metric: str, cur_value: float,
                pct: float) -> dict:
        """突变检测：当前待评估值 与 稳健基线(窗口值中位数)之差占基线比例 > pct。

        用**中位数**而非均值作基线——对极端尖峰鲁棒（借鉴 DataBuff 避免告警风暴：
        基线被尖峰污染会把回落正常值也误判为突变，导致永不恢复）。恢复时值回到
        中位数附近(偏差 ≤ pct)即对称判定为已恢复。

        返回 {detected, prev_avg, cur, pct_used}。
        """
        win = self.store.window(device_id, metric, minutes=10)
        if len(win) < 2:
            return None
        vals = sorted(r["value"] for r in win)
        n = len(vals)
        base = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
        if base == 0:
            return {"detected": False, "prev_avg": base, "cur": cur_value,
                    "pct_used": None}
        chg = abs((cur_value - base) / base) * 100
        return {"detected": chg > pct, "prev_avg": round(base, 2),
                "cur": cur_value, "pct_used": round(chg, 1)}

    def _evaluate_rule(self, device_id, metric, value, rule, trig, a_type, ts, raised):
        ts = ts or _now_ts()
        # 找该规则现有未恢复告警
        open_a = next((a for a in self.store._alerts
                       if a["device_id"] == device_id and a["metric"] == metric
                       and a["state"] == "firing"), None)
        if trig:
            if open_a is None:
                # 新触发
                aid = f"AL-{device_id}-{metric}-{int(time.time())}"
                alert = {"id": aid, "device_id": device_id, "metric": metric,
                         "type": a_type, "value": value,
                         "op": rule["op"], "threshold": rule["threshold"],
                         "level": rule["level"], "state": "firing",
                         "raised_at": ts, "recovered_at": None,
                         "events": [{"ts": ts, "event": f"触发({a_type})",
                                     "value": value}]}
                self.store._alerts.append(alert)
                self.store._save("_alerts", "alerts_file", self.store._alerts)
                raised.append(alert)
            else:
                # 持续触发，更新最新值
                open_a["value"] = value
                open_a["events"].append({"ts": ts, "event": "持续触发",
                                         "value": value})
                self.store._save("_alerts", "alerts_file", self.store._alerts)
        elif open_a is not None:
            # 恢复自动关闭
            open_a["state"] = "recovered"
            open_a["recovered_at"] = ts
            open_a["events"].append({"ts": ts, "event": "恢复",
                                     "value": value})
            self.store._save("_alerts", "alerts_file", self.store._alerts)
            # 自动关闭关联工单
            self._close_ticket_for(device_id, metric, ts)

    def _close_ticket_for(self, device_id, metric, ts) -> None:
        for t in self.store._tickets:
            if (t["device_id"] == device_id and t["metric"] == metric
                    and t["state"] != "done"):
                t["state"] = "done"
                t["done_at"] = ts
                t["events"].append({"ts": ts, "event": "done(恢复自动关闭)"})
        self.store._save("_tickets", "tickets_file", self.store._tickets)

    # ---- 批量评估（定时任务）----
    def evaluate(self, ts: str = None) -> dict:
        """定时评估全部已记录指标的规则（回看最近数据，不编造）。"""
        raised, closed = [], 0
        seen = set()
        for r in self.store._metrics:
            key = (r["device_id"], r["metric"])
            if key in seen:
                continue
            seen.add(key)
            latest = self.store.latest(r["device_id"], r["metric"])
            if latest:
                raised += self.evaluate_point(r["device_id"], r["metric"],
                                              latest["value"], ts)
        return {"raised": len(raised), "alerts": raised,
                "firing": len(self.store.alerts("firing"))}

    # ---- 告警 → 工单 ----
    def alert_to_ticket(self, alert: dict) -> dict:
        """触发工单：state=open，自动建工单。"""
        problem = (f"设备 {alert['device_id']} 指标 {alert['metric']} "
                   f"异常({alert['type']}) 值={alert['value']}")
        t = {"id": f"TK-{alert['device_id']}-{alert['metric']}",
             "device_id": alert["device_id"], "metric": alert["metric"],
             "problem": problem, "severity": alert["level"],
             "state": "open", "triage": "待诊断",
             "diagnosis": "", "resolution": "",
             "alert_id": alert["id"], "ts": alert["raised_at"],
             "done_at": None,
             "events": [{"ts": alert["raised_at"], "event": "open(告警触发)"}]}
        # 去重：同一设备指标已有 open/in_progress 工单则复用
        for exist in self.store._tickets:
            if exist["device_id"] == alert["device_id"] and \
               exist["metric"] == alert["metric"] and exist["state"] != "done":
                return exist
        self.store._tickets.append(t)
        self.store._save("_tickets", "tickets_file", self.store._tickets)
        return t

    # ---- 工单状态机 open → in_progress → done ----
    def ticket_state(self, ticket_id: str, target: str, note: str = "") -> dict:
        """推进工单状态机：open → in_progress → done（合法流转）。"""
        t = next((x for x in self.store._tickets if x["id"] == ticket_id), None)
        if t is None:
            return {"error": f"工单不存在: {ticket_id}"}
        valid = {"open": {"in_progress", "done"},
                 "in_progress": {"done"},
                 "done": set()}
        if target not in valid.get(t["state"], set()):
            return {"error": f"非法流转: {t['state']} → {target}",
                    "id": ticket_id, "state": t["state"]}
        t["state"] = target
        if target == "done":
            t["done_at"] = _now_ts()
        t["events"].append({"ts": _now_ts(), "event": f"{target}({note})" if note else target})
        self.store._save("_tickets", "tickets_file", self.store._tickets)
        return t

    def resolve_ticket(self, ticket_id: str, resolution: str) -> dict:
        t = next((x for x in self.store._tickets if x["id"] == ticket_id), None)
        if t is None:
            return {"error": f"工单不存在: {ticket_id}"}
        t["resolution"] = resolution
        t["diagnosis"] = t["diagnosis"] or resolution
        t["state"] = "done"
        t["done_at"] = _now_ts()
        t["events"].append({"ts": _now_ts(), "event": "done(处理完成)",
                            "resolution": resolution})
        self.store._save("_tickets", "tickets_file", self.store._tickets)
        return t


# ═══════════════════════════════════════════════════════════════════════
# 3. MQTT 接入抽象（Source 接口，可对接真实 MQTT/传感器/OPC UA）
# ═══════════════════════════════════════════════════════════════════════
class Source:
    """接入源抽象接口：统一『设备数据 → 存储 → 评估告警 → 触发工单』入口。

    子类实现 poll()/connect()/close()；本类提供 run_cycle 把一条数据走完整链路。
    真实 MQTT(需 paho-mqtt)、OPC UA、传感器都实现本接口即可无缝接入。
    """

    def __init__(self, store: MetricStore = None, engine: AlertEngine = None,
                 auto_ticket: bool = True):
        self.store = store or MetricStore()
        self.engine = engine or AlertEngine(self.store)
        self.auto_ticket = auto_ticket

    # ---- 子类需实现 ----
    def connect(self):
        return True

    def poll(self) -> list:
        """返回待处理的数据点列表 [{device_id, metric, value, ts?}]。"""
        return []

    def close(self):
        pass

    # ---- 统一数据流（收到一条 → 存储 → 评估 → 触发工单）----
    def run_cycle(self, batch: list = None) -> dict:
        """一次采集评估循环。batch 缺省用 self.poll()。"""
        batch = batch if batch is not None else self.poll()
        n_ingest, n_alert, n_ticket = 0, 0, 0
        for pt in batch:
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

    # ---- 简化：直接喂一条数据（测试/单点用）----
    def feed(self, device_id: str, metric: str, value: float) -> dict:
        return self.run_cycle([{"device_id": device_id, "metric": metric,
                                "value": value}])


class MockSensor(Source):
    """模拟传感器源：按脚本生成设备指标（演示/测试用，零依赖）。"""

    def __init__(self, devices: list = None, metrics: list = None,
                 base: dict = None, noise: float = 0.0, **kw):
        super().__init__(**kw)
        self.devices = devices or ["d1", "d2"]
        self.metrics = metrics or ["temperature", "vibration", "power"]
        self.base = base or {"temperature": 45.0, "vibration": 2.0, "power": 30.0}
        self.noise = noise
        self._step = 0

    def poll(self) -> list:
        import random
        batch = []
        for d in self.devices:
            for m in self.metrics:
                base = self.base.get(m, 0.0)
                v = base + random.uniform(-self.noise, self.noise)
                if m == "power":
                    v = base + self._step * 1.5  # 功率递增模拟趋势
                batch.append({"device_id": d, "metric": m,
                              "value": round(v, 1)})
        self._step += 1
        return batch


# ═══════════════════════════════════════════════════════════════════════
# 4. AI 问数最小版 MonitorAsk（自然语言查设备/告警）
# ═══════════════════════════════════════════════════════════════════════
_METRIC_ALIAS = {
    "温度": "temperature", "温": "temperature", "temp": "temperature",
    "振动": "vibration", "震动": "vibration",
    "功率": "power", "负载": "power",
    "cpu": "cpu_percent", "内存": "mem_percent", "mem": "mem_percent",
    "连接": "connection", "状态": "status",
}


class MonitorAsk:
    """AI 问数最小版：自然语言查设备/告警/指标。

    借鉴 DataBuff「智能问数专家 queryMetricData / queryServiceAlarms」语义，
    用**确定性关键词路由 + 真实存储查询**（先查库再回答，禁止幻觉），零 LLM 可答。
    支持三类问法：
      - 设备指标：X设备温度 / 温度最高的设备 / 哪台设备温度过高
      - 告警查询：最近有哪些告警 / 还在触发中的告警
      - 工单查询：有哪些待处理工单
    """

    def __init__(self, store: MetricStore = None, engine: AlertEngine = None):
        self.store = store or MetricStore()
        self.engine = engine or AlertEngine(self.store)

    def ask(self, question: str) -> dict:
        """自然语言入口 → 路由 → 查真实数据 → 答案。"""
        q = question.strip()
        hits = {"温度": 1, "振动": 1, "功率": 1, "cpu": 1, "内存": 1,
                "连接": 1, "指标": 1}
        metric = self._extract_metric(q)

        # 1) 告警查询
        if any(k in q for k in ("告警", "报警", "异常", "触发")):
            return self._ask_alerts(q, metric)
        # 2) 工单查询
        if any(k in q for k in ("工单", "待处理", "待办")):
            return self._ask_tickets(q)
        # 3) 设备指标查询（含极值/过高/最新）
        if metric or any(k in q for k in ("设备", "最高", "最高", "过高",
                                          "最新", "多少", "状态")):
            return self._ask_metric(q, metric)
        return {"mode": "miss", "answer": f"未能理解问题（可问：哪台设备温度过高 / 最近有哪些告警）: {q}"}

    def _extract_metric(self, q: str):
        for cn, en in _METRIC_ALIAS.items():
            if cn in q:
                return en
        # 纯字母指标名
        m = re.search(r"\b([a-z_]+)\b", q.lower())
        return m.group(1) if m else None

    def _ask_alerts(self, q, metric) -> dict:
        state = "recovered" if "已恢复" in q or "恢复" in q else None
        alerts = self.store.alerts(state, limit=20)
        if metric:
            alerts = [a for a in alerts if a["metric"] == metric]
        if not alerts:
            return {"mode": "alert", "answer": "当前没有相关告警记录",
                    "alerts": [], "count": 0}
        lines = []
        for a in alerts[:8]:
            st = "触发中" if a["state"] == "firing" else "已恢复"
            lines.append(f"  - {a['device_id']}.{a['metric']} "
                         f"[{a['type']}] 值={a['value']} {st}")
        return {"mode": "alert", "answer": f"共 {len(alerts)} 条告警：\n" + "\n".join(lines),
                "alerts": alerts, "count": len(alerts)}

    def _ask_tickets(self, q) -> dict:
        state = None
        if "处理中" in q:
            state = "in_progress"
        elif "待处理" in q or "待办" in q or "未处理" in q or "开放" in q or "待" in q:
            state = "open"
        tickets = self.store.tickets(state)
        if not tickets:
            return {"mode": "ticket", "answer": "没有相关工单", "tickets": [],
                    "count": 0}
        lines = [f"  - {t['id']} {t['problem']} [{t['state']}]" for t in tickets[:8]]
        return {"mode": "ticket", "answer": f"共 {len(tickets)} 张工单：\n" + "\n".join(lines),
                "tickets": tickets, "count": len(tickets)}

    def _ask_metric(self, q, metric) -> dict:
        # 过高/超阈值 → 查触发中的告警设备
        if any(k in q for k in ("过高", "超阈值", "异常", "超标", "太高")):
            alerts = self.store.alerts("firing")
            if metric:
                alerts = [a for a in alerts if a["metric"] == metric]
            if not alerts:
                return {"mode": "metric", "answer": f"当前没有{metric or '任何'}指标超阈值的设备",
                        "devices": [], "count": 0}
            devs = sorted({a["device_id"] for a in alerts})
            vals = {a["device_id"]: a["value"] for a in alerts}
            lines = [f"  - {d} {metric or '异常指标'} 值={vals[d]}" for d in devs]
            return {"mode": "metric", "answer": f"以下设备{metric or '指标'}过高：\n" + "\n".join(lines),
                    "devices": devs, "count": len(devs)}
        # 最高/最新
        if any(k in q for k in ("最高", "最大", "最新")):
            if not metric:
                return {"mode": "miss", "answer": "请指定指标（如：温度最高的设备）"}
            best = None
            for d in self.store.devices():
                lat = self.store.latest(d, metric)
                if lat:
                    if best is None or lat["value"] > best["value"]:
                        best = {"device_id": d, "value": lat["value"],
                                "ts": lat["ts"], "metric": metric}
            if best is None:
                return {"mode": "metric", "answer": f"暂无 {metric} 指标数据",
                        "device": None}
            return {"mode": "metric",
                    "answer": f"{metric} 最高的是 {best['device_id']} 值={best['value']}（{best['ts']}）",
                    "device": best}
        # 最新值
        if metric:
            out = []
            for d in self.store.devices():
                lat = self.store.latest(d, metric)
                if lat:
                    out.append({"device_id": d, "value": lat["value"],
                                "ts": lat["ts"]})
            if not out:
                return {"mode": "metric", "answer": f"暂无 {metric} 指标数据",
                        "devices": []}
            lines = [f"  - {o['device_id']} {metric}={o['value']}（{o['ts']}）" for o in out]
            return {"mode": "metric", "answer": f"设备 {metric} 最新值：\n" + "\n".join(lines),
                    "devices": out}
        return {"mode": "miss", "answer": f"未识别指标或设备: {q}"}


# ═══════════════════════════════════════════════════════════════════════
# 5. 一站式：演示/接入工厂本体决策
# ═══════════════════════════════════════════════════════════════════════
def run_demo(devices=None, metrics=None, rounds: int = 12,
             temp_high: float = 80.0, dir: str = None) -> dict:
    """端到端演示：模拟设备数据 → 存储 → 告警评估 → 触发工单 → AI问数。

    返回全链路摘要。
    """
    store = MetricStore(dir or DEFAULT_DIR)
    engine = AlertEngine(store)
    for d in (devices or ["d1", "d2"]):
        store.set_rule(d, "temperature", ">", temp_high, level="high",
                       mutate_pct=20.0, label=f"{d} 温度过高")
        store.set_rule(d, "power", "<", 5.0, level="medium")
    # 模拟：温度从低逐步升到超阈值（触发阈值告警 + 突变），功率骤降（触发阈值）
    src = MockSensor(devices=devices or ["d1", "d2"],
                     metrics=["temperature", "power"],
                     base={"temperature": 40.0, "power": 30.0}, **{"store": store, "engine": engine})
    ts0 = datetime.now() - timedelta(minutes=rounds)
    history = []
    # 先补历史基线（突变检测需要）
    for i in range(6):
        ts = (ts0 + timedelta(minutes=i)).isoformat(timespec="seconds")
        for d in (devices or ["d1", "d2"]):
            store.record(d, "temperature", 40 + i * 0.5, ts)
    for i in range(rounds):
        for d in (devices or ["d1", "d2"]):
            temp = 40 + i * 4 if i < 10 else 95  # 逐步升高越过 80 阈值
            store.record(d, "temperature", temp)
        # 每轮评估 + 告警自动建工单
        res = engine.evaluate()
        for alert in res["alerts"]:
            engine.alert_to_ticket(alert)
    # 功率骤降触发阈值 + 建工单
    for d in (devices or ["d1", "d2"]):
        store.record(d, "power", 2.0)
    res = engine.evaluate()
    for alert in res["alerts"]:
        engine.alert_to_ticket(alert)

    ask = MonitorAsk(store, engine)
    q1 = ask.ask("哪台设备温度过高")
    q2 = ask.ask("最近有哪些告警")
    q3 = ask.ask("温度最高的设备")
    return {"store": store, "engine": engine, "ask": ask,
            "metrics": len(store._metrics),
            "firing_alerts": len(store.alerts("firing")),
            "total_alerts": len(store._alerts),
            "tickets": len(store._tickets),
            "q_high_temp": q1, "q_alerts": q2, "q_max_temp": q3}
