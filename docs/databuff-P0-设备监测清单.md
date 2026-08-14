# DataBuff 融入 P0 实施清单（设备监测骨架）

> 借鉴 DataBuff「指标采集 → 统一存储 → AI问数 → 告警」骨架，落地到工厂设备监测，
> 扩大本体决策系统 + solo 工具包。**零依赖、纯标准库**；**不引入 DataBuff 本身**
> （AGPL-3.0），仅借鉴设计思路，规避 AGPL 传染。
>
> 实现位置：`solo/factory/monitor.py` + CLI 命令 `monitor-demo/ask/ingest` + 单测 `tests/test_monitor.py`
> 报告依据：`C:/Users/ASUS Air/_os/databuff-research.md`

---

## 一、P0 实施清单（5 项全部完成）

| # | 事项 | DataBuff 借鉴 | 实现 | 落地 |
|---|------|--------------|------|------|
| **P0-1** | **统一指标存储** | Doris 时序存储 + 分钟预聚合 | `MetricStore`：`device_metric` 时序模型 `{device_id, metric, value, ts, tags}`，JSON 持久化，`record/series/latest/window/aggregate(分钟预聚合)` | ✅ |
| **P0-2** | **告警评估引擎** | 阈值 + 突变检测 + 事件记录 | `AlertEngine`：阈值告警 + 突变检测（中位数稳健基线环比）+ **恢复自动关闭**，告警记录含 `events[]` 事件链（触发/持续/恢复） | ✅ |
| **P0-3** | **工单状态机补全** | 事件记录 → 工单闭环 | `alert_to_ticket` 告警→工单 + 状态机 **open→in_progress→done**（合法流转校验，恢复自动关闭工单） | ✅ |
| **P0-4** | **MQTT 接入抽象** | OTLP 双协议接入层思路 | `Source` 抽象接口（connect/poll/close/run_cycle）+ `MockSensor`（零依赖模拟）；真实 MQTT/OPC UA 实现该接口即可接入 | ✅ |
| **P0-5** | **AI 问数最小版** | 智能问数专家 queryMetricData/queryServiceAlarms | `MonitorAsk`：自然语言查设备/告警/工单，**确定性关键词路由 + 先查库再回答**（禁幻觉），零 LLM 可答 | ✅ |

**数据流（DataBuff 同构骨架）**：
```
接入源(Source) → 统一指标存储(MetricStore, device_metric 时序)
    → 告警评估引擎(AlertEngine: 阈值 + 突变检测 + 恢复自动关闭)
    → 工单状态机(open → in_progress → done) + AI问数(MonitorAsk)
```

---

## 二、五大模块详解

### 1. 统一指标存储 `MetricStore`
- 记录模型 `device_metric = {device_id, metric, value, ts, tags}`（对齐 DataBuff 指标模型，抽象为「设备-指标-标签」而非照搬 service/instance）
- 持久化到 `~/.solo/monitor/metrics.json`（原子写，可审计）
- **分钟级预聚合** `aggregate()`：借鉴 DataBuff「分钟预聚合查询快、存储省、告警评估高效」——按分钟桶取均值/min/max/count
- `ingest()` 统一接入入口，`latest()/series()/window()/devices()` 查询面

### 2. 告警评估引擎 `AlertEngine`
- **规则表**：`{device_id, metric, op(>/<), threshold, level, mutate_pct, label}`，阈值 + 突变检测同一规则可配
- **阈值告警**：最新值 op threshold → 触发（level: high/medium）
- **突变检测**：当前值与**窗口值中位数**偏差率 > mutate_pct → 触发
  - ⚠️ **关键坑（本会话实测踩中）**：突变基线必须用**中位数**而非均值。均值被极端尖峰污染后，回落正常值也会被误判为突变 → 永不恢复 → 告警风暴（正是 DataBuff 报告警示点）。中位数对尖峰鲁棒，触发/恢复对称判定。
- **恢复自动关闭**：值回到阈值内 / 回到中位数附近 → 告警标记 `recovered` + 自动关闭关联工单
- **事件记录**：每条告警带 `events[]`（触发/持续触发/恢复），对齐 DataBuff「记录触发、恢复、状态变化」

### 3. 工单状态机补全（open→in_progress→done）
- `alert_to_ticket(alert)`：告警触发 → 自动建工单（state=open，按设备+指标去重防重复建单）
- `ticket_state()`：合法流转校验 `open→{in_progress,done}`、`in_progress→{done}`、`done→{}`（非法流转拒绝）
- 恢复自动关闭：指标恢复正常 → 关联工单自动置 done + 记录 done_at

### 4. MQTT 接入抽象 `Source`
- 抽象接口：`connect()/poll()/close()/run_cycle(batch)`，统一「收到数据 → 存储 → 评估告警 → 触发工单」链路
- `run_cycle()` 返回 `{ingest, alerts, tickets}` 统计
- `MockSensor`：零依赖模拟传感器源（测试/演示用）
- **真实接入**：实现 `Source.poll()`（MQTT 用 paho-mqtt 订阅 topic、OPC UA 轮询节点）即可无缝接入，其余链路零改动

### 5. AI 问数最小版 `MonitorAsk`
- 借鉴 DataBuff「AI 直接读真实数据、禁止裸 LLM 下结论」原则：**确定性关键词路由 + 先查库再回答**
- 支持问法：`哪台设备温度过高` / `最近有哪些告警` / `温度最高的设备` / `有哪些待处理工单`
- 返回 `{mode, answer, ...真实数据}`，mode ∈ {metric/alert/ticket/miss}
- 指标中英别名表 `_METRIC_ALIAS`（温度→temperature 等）

---

## 三、CLI 命令

```bash
solo monitor-demo --rounds 12 --temp-high 80.0   # 端到端演示：数据→告警→工单→AI问数
solo monitor-ask "哪台设备温度过高"              # AI问数（自然语言查设备/告警/工单）
solo monitor-ingest d1 temperature 95.0          # 接入一条设备指标（自动评估告警→建工单）
```

---

## 四、实测结果（真实执行）

### 单测 `tests/test_monitor.py`（16 项全过）
覆盖：指标存储（record/series/aggregate）、阈值告警、突变检测、恢复自动关闭、工单状态机（含非法流转拒绝、恢复自动关闭工单）、Source 全链路、AI问数（过高设备/告警列表/最高值/待处理工单/未知问题 miss）。

### 端到端实测（隔离目录，设备 d1/d2）
```
[1] 数据接入  指标总量=26, 分钟预聚合=4桶, 触发中告警=4, open工单=4
[2] 状态机    TK-d1-temperature: open → in_progress → done（非法 done→open 被拒）
[3] 恢复关闭  指标回正常 → firing 4→0, recovered=4, open工单→0, done工单=4
[4] AI问数    温度过高设备 / 告警列表 / 温度最高设备 / 待处理工单 / 已完成工单 全部答对
```

### 全量回归
`python -m pytest -q` → **203 passed**（含新增 16 项，未破坏既有模块）

---

## 五、合规与边界

- **许可证**：零 DataBuff 代码，仅借鉴设计思路（指标模型、告警状态机、问数语义），无 AGPL 传染风险。
- **领域差异**：把 DataBuff 的「服务/实例/Trace」映射为「设备/产线/传感器」，抽象「设备-指标-标签」模型。
- **AI 可信度**：AI 问数走**确定性路由 + 先查库再回答**，禁止裸 LLM 下结论。
- **告警风暴**：中位数稳健基线 + 恢复自动关闭 + 同设备同指标工单去重，三重防误报。
- **存储规模**：JSON 持久化适合中小设备量；设备量大时 `MetricStore` 存储层可替换为 SQLite/Doris（接口不变）。

---

## 六、后续（P1，未在本清单内）

P1 建议：告警→AI 诊断闭环（LLM 写回 diagnosis）、巡检报告、solo 作 MCP Server 暴露设备/告警/工单工具、集成真实 MQTT/OPC UA。
