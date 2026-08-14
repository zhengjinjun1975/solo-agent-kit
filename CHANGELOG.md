# Changelog

所有显著变更记录在此。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased] - 2026-08-14

### 新增：设备监测 web 化 + 防断链（一切归结到 web）

- Web `/api/monitor/metrics|alerts|tickets`（GET）：设备指标看板快照 / 告警列表 / 工单列表
- Web `/api/monitor/ingest|rule|ask|ticket-state|demo`（POST）：模拟接入指标(全链路) / 设告警规则 / AI问数 / 推进工单状态机 / 一键端到端演示
- 前端「监控」面板新增设备监测区：指标看板 / 告警 / 工单(含状态机推进) / 模拟ingest / 设规则 / AI问数 / 一键演示
- 防断链：`ingest→指标存储→告警→工单状态机→AI问数` 全链路在 web 可操作；CLI(monitor-demo/ask/ingest) 与 web 双入口共用 `solo/factory/monitor` 同一实现
- `MetricStore` 数据目录可用环境变量 `SOLO_MONITOR_DIR` 覆盖（web/e2e 测试隔离，不污染 ~/.solo/monitor）
- 新增 `monitor_snapshot()` 看板快照助手 + `tests/test_monitor_web.py`（web 全链路防断链 e2e，5 例）

### 新增：改行业→自动重建产物（事件驱动无死角）

- `industry-set <行业> [csv]`：改行业事件驱动入口，一步 ①持久化"当前行业" ②自动重建 D0问题集/D1词典(工厂lexicon)/D4报告/决策阈值 ③按"行业+kb"隔离落盘产物包（跨行业不覆盖/串台）
- `industry-current`：查看当前行业及生效配置
- "当前行业"持久化状态（`~/.solo/current_industry.json`）：改行业后，任何**省略 `--industry`** 的 draft-questions/lexicon-draft/report-draft/决策**自动跟随当前行业**，杜绝"改行业仍旧行业产物"的串台死角
- Web `/api/decisions` 透传可选 `industry`（未传时跟随当前行业）

## [0.5.6] - 2026-08-13

### 新增(合并远程v0.8.x功能 + 本地FDE交付辅助, 版本统一0.5.6)

- 保留远程 v0.8.x 全部功能：外部插件体系(Obsidian/Excel报表/网络扫描/协议探针)、前端厂区面板、writing 优化器、竞品分析
- FDE交付辅助: draft-questions(评测题)/lexicon-draft(词典草稿)/report-draft(报告草稿)
- FDE套件运行手册

## 历史版本

- **0.8.x（2026-08-10/11）**：外部插件体系（Obsidian/Excel报表/网络扫描/协议探针）、前端厂区面板、writing 优化器、竞品分析（功能已并入 0.5.6）
- **0.6.x-0.7.x（2026-08-10）**：FDE 现场能力深化（远程运维/工单闭环/环境监控/日志诊断）、代码审查 P0/P1/P2 修复（功能已并入 0.5.6）
- **0.5.x（2026-08-10）**：UI 美观度优化、记忆清理、导航图标针对性设计
- **0.4.x 及更早**：本体优先定位确立、三层两域记忆、skill 提取、六维写作检查、代码影响分析等早期演进

（完整历史可在 git 提交中回溯；0.5.6 为当前发布版本，统一了版本线。）
