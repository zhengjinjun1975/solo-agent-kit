# solo 三大开源联动 + FDE 深度补强（收尾实测）

> 收尾：修复 diagnose-kb 扫描注册 + 跨开源组装链全绿 + 4 新原子实测 + pytest 全绿 + 推送。
> 仓库：`E:/open-source/solo-agent-kit` ｜ 关联兄弟仓库：`factory-ontology-kit`、`sme-decision-ontology`

---

## 1. 背景：三大开源联动 + FDE 深度补强

`factory-ontology-kit`（本体/认知/RAG）、`sme-decision-ontology`（决策/阈值回灌）、`solo-agent-kit`
（监测/工单/交付）三大开源仓库，经 `fde_runtime/linkage.py` 统一能力路由实现「算法开源联动、数据不出厂」的跨仓库协同。

本轮补强把 FDE（工厂数据工程）认知/决策/监测/诊断深度补齐为 4 个新原子，并装配成一条跨开源组装链：

```
monitor → factory → sme → fde → diagnose → delivery
 指标采集  本体认知   决策行动  工单诊断   故障知识库  交付验收
```

**边界铁律**：联动传「算法入参」（问题/路径），各库数据本地自持（data/），**数据不出厂**；
开源原子禁依赖闭源原子（`loader.check_open_source_boundary`）。

---

## 2. 4 个新原子

| 原子 | 能力 | 复用来源 | 说明 |
|------|------|----------|------|
| `monitor-anomaly` | `monitor.anomaly` | solo | 时序异常检测（趋势/突跳/多变量马氏距离）+ 预测性维护雏形（RUL/健康指数） |
| `factory-cognition` | `factory.cognition` | factory-ontology-kit | 确定性本体问答优先 + 离线 RAG 降级（先查库再答防幻觉） |
| `sme-decision` | `sme.decision` | sme-decision-ontology | 决策 / 阈值回灌（preview 不落盘）/ 告警→决策→行动一键链 |
| `diagnose-kb` | `diagnose.kb` | solo | 故障知识库「learn→diagnose→根因分析」，未知症状诚实 miss（防幻觉） |

---

## 3. 本轮修复点

### 3.1 diagnose-kb 扫描注册问题（核心修复）
- **症状**：`diagnose-kb` 原子未出现在 `registry.json`，`registry loader`（`scan_atoms`）扫描不到。
- **根因**：`atoms/fde/diagnose-kb/` 只有 `main.py`，缺 `manifest.json`；`scan_atoms` 按 `manifest.json`
  发现原子，缺清单即容错跳过 → 不进 registry、`run_capability("diagnose.kb", ...)` 报「能力未提供」。
- **修复**：补 `atoms/fde/diagnose-kb/manifest.json`（name/agent/version/entry/license/open_source/
  provides/capabilities），并重跑 `scan → write_registry → load`，registry 原子数 **14 → 15**，
  `diagnose.kb` 能力成功注册。

### 3.2 跨仓库 `core` 模块名冲突（联动健壮性兜底）
- **症状**：`sme.decision.decide` 在 factory 本体问答先执行后报
  `No module named 'core.domain_model'`（单测隔离通过、整链跑失败）。
- **根因**：`factory-ontology-kit/codes/core/` 是**常规包**（含 `__init__.py`），
  `sme-decision-ontology/codes/core/` 是**命名空间包**（无 `__init__.py`）。
  两份 codes 同时入 `sys.path` 时，`import core` 命中先导入的常规包（factory），
  `from core.domain_model import ...` 便找不到模块。
- **修复**：`linkage.py` 新增 `codes_isolation(repo_root)` 上下文管理器——把目标 codes 置 `sys.path`
  首位、临时移除其它兄弟 codes、清掉 `core` 缓存使导入精确命中目标仓库，运行后恢复。
  `sme-decision`（decide/action/feedback）与 `factory-cognition`（ontology_qa）均改用它。

### 3.3 monitor-anomaly 两处缺陷
- **平坦序列除零**：`detect_sudden` 对全等序列（MAD=0 且 stdev=0）时 scale=0 → 除零崩溃。
  修复 `_mad`：MAD 为 0 回退 stdev，仍为 0 用 `1e-9` 兜底，平坦序列诚实返回 `anomaly=False`。
- **trend 阈值误用**：原子 `detect` 统一默认 `k=3.0`（sudden 的 z-score 阈值），
  trend 的归一化斜率阈值本应为 `0.8` → trend 永不触发。修复：未显式传 k 时按模式取各自默认。

---

## 4. 实测结果

### 4.1 组装链 run_flow 全绿（`assemblies/solo-linkage-workflow.json`）
新增 `learn` 步骤（先沉淀故障知识），链路 12 步全部 `ok`，`loop_closed=True`，`accept=True`：

```
  ingest     monitor.metric      -> ok
  anomaly    monitor.anomaly     -> ok sudden_anomaly=True
  predict    monitor.anomaly     -> ok rul=37.79
  adaptive   monitor.alert       -> ok thr=8.72
  set_rule   monitor.alert       -> ok
  evaluate   monitor.alert       -> ok
  cognition  factory.cognition   -> ok source=ontology ans=振动信息:...
  decision   sme.decision        -> ok decision=维护告急 actions=[{type:'维护工单',...}]
  ticket     fde.task            -> ok
  learn      diagnose.kb         -> ok
  diagnose   diagnose.kb         -> ok hit=True cause=轴承磨损/泵轴对中不良
  package    delivery.package    -> ok
```

跨开源协同：`cognition` 命中 factory 本体（`source=ontology`）；`decision` 产出真实维护行动；
`diagnose` 命中故障库根因；交付包工单注入诊断根因（前一环输出=后一环输入）。

### 4.2 单测与回归
- 新增 `tests/test_fde_linkage_deepen.py`：**23 用例**（4 新原子真实数据 + 跨仓库流 + 边界断言）。
- 回归 `python -m pytest tests/`：**261 passed**（238 基线 + 23 新增），全绿。

### 4.3 原子独立自测
```
monitor-anomaly 独立自测通过, 0 失败
diagnose-kb     独立自测通过, 0 失败
factory-cognition 独立自测通过, 0 失败  (ontology_qa: 一共有 37 条记录)
sme-decision    独立自测通过, 0 失败  (feedback preview: 12.6)
```

---

## 5. 交付清单

- 修复 `atoms/fde/diagnose-kb/manifest.json`（诊断原子注册）
- 增强 `fde_runtime/linkage.py`（`codes_isolation` 跨仓库导入隔离）
- 修复 `atoms/monitor/monitor-anomaly/main.py`（平坦除零 + trend 阈值）
- 增强 `atoms/decision/sme-decision/main.py`、`atoms/cognition/factory-cognition/main.py`（隔离导入）
- 新增 `assemblies/solo-linkage-workflow.json` `learn` 步骤（learn→diagnose→根因闭环）
- 重生成 `registry.json`（15 原子）
- 新增 `tests/test_fde_linkage_deepen.py`（23 用例）
- 落盘本文档 `_os/solo-fde-linkage-deepen.md`
- 推送 GitHub
