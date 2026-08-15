# SoloAgentKit 架构文档

> 针对 FDE（工厂部署工程师）/一人公司的轻量全栈 AI 工具。零第三方依赖（纯标准库）。
> 本文档面向工程师：模块分层、契约、数据流、扩展方式。

## 0. 原子化定位（fde 域开源原子底座）

本仓库在生态「插件式原子智能体组装」架构中，作为 **FDE 域的开源原子底座**存在
（架构定稿见 `_os/plugin-agent-architecture.md`、边界见 `_os/oss-close-boundary-license.md`）。

**四条定位，贯穿本文档与 README：**

1. **fde 域原子**：solo 本身是一个开源超集原子（`agent.type=fde`，`open_source=true`），内部按子能力域再拆原子——
   `fde`（现场流程 D0-D4 工具箱）、`memory`（三层两域记忆）、`monitor`（设备监测）、`write`（中文写作）
   四原子可独立运行、可被上层组装。每个原子 = 现有核心模块（零改动）+ `manifest.json` + `main.py` 薄壳。
2. **甲方乙方工程师共用工具**：solo 不是只给乙方（FDE 交付）用，也不只给甲方自持用——同一套开源底座，
   乙方工程师用于交付辅助（起草/记忆/方法论），甲方工程师用于自持自运行（本体/监测/决策），两方共用同一算法内核。
3. **开源算法 + 闭源编排边界**：算法/流程内核全部开源（Apache-2.0，可免费使用、被闭源编排层调用）；
   唯一不进开源的是「编排/组装/交付增值」（assembler/orchestrator/deliver）——闭源侧只经公开能力接口调用本仓库原子，
   **禁 import 内部、禁依赖反向**。删掉闭源编排器后，本仓库全开源子图仍自洽可独立运行。
4. **FDE 先开源**：solo 的算法与流程内核优先开源，甲方可自持；其「对外服务/交付」增值若需闭源，由闭源 `deliver`
   原子承接，不把 FDE 本身闭源化。

> 边界铁律（开源侧强制执行）：开源原子**不得** `depends_on` 任何闭源原子；所有外部依赖同为开源侧且可离线获得。
> 本仓库核心模块零依赖（纯标准库），天然满足「开源可独立运行」。

## 1. 分层架构

```
┌─────────────────────────────────────────────┐
│  Interface 层（入口）                        │
│  cli.py 命令行 │ web_server.py HTTP │ 前端    │
└───────────────────┬─────────────────────────┘
                    │
┌───────────────────▼─────────────────────────┐
│  Application 层（编排）                     │
│  agent.py AI路由 │ registry.py 能力注册表    │
└───────────────────┬─────────────────────────┘
                    │
┌───────────────────▼─────────────────────────┐
│  Domain 层（方法论能力）                    │
│  memory/skill/writing/code/gen/task/        │
│  factory{clean,stats,ontology}              │
└───────────────────┬─────────────────────────┘
                    │
┌───────────────────▼─────────────────────────┐
│  Infrastructure 层（基础）                  │
│  provider 模型 │ data_connector 数据源 │     │
│  base(原子写/日志/错误) │ diagnostics        │
└─────────────────────────────────────────────┘
```

## 2. 模块契约

### 基础设施（solo/base.py）
- `atomic_write(path, data)`：原子写 JSON（临时文件+os.replace）
- `lock_for(path)`：按路径并发锁
- `get_logger(name)`：统一格式日志
- `ApiError(code, msg)` / `DataSourceError`：统一错误契约

### 数据源（solo/data_connector.py）
- `connect(source) -> list[dict]`：读 CSV/SQLite/SQL，失败抛 DataSourceError
- `list_tables(db_path)`：SQLite 表列表
- 安全：SQL 仅允许 SELECT（白名单）

### 模型分层（solo/provider.py）
- `Provider.from_file()`：从 provider.yaml 读配置
- `complete(prompt, tier)`：tier=local/remote/auto
- `embed(text)`：向量化（记忆检索用）

### 能力（应用层通过 registry 调度）
| 模块 | 能力 | 数据 |
|---|---|---|
| factory/clean | 数据清洗 | DataCleaner → CleanReport |
| factory/stats | 数据分析 | describe → DescribeResult |
| factory/ontology | 本体建模 | from_rows → 三元组 |
| memory | 三层两域记忆 | search(embed优先) |
| skill | 可复用经验 | all_details |
| writing | 六维写作检查 | scan → {passed, dimension} |
| code | 代码影响分析 | CodeGraph.impact |
| gen | 代码/文档生成 | generate_code/doc |
| task | 任务状态控制面 | 断点续跑 |

## 3. 返回契约

- Web API：`{data...}` 成功；`{"error": msg, "code": N}` 失败（ApiError）
- Agent：`{"intent": ..., "data": ..., "ok": bool}`
- CLI：JSON + 分级退出码（0成功/1用户错误/2网络/3认证/4其他）

## 4. 数据流

### 数据能力（清洗/分析/建模）
```
前端选数据源 → /api/browse(硬盘浏览) → 选文件/表
  → /api/datasource-columns(列检测) → 选列
  → /api/clean|stats|ontology(执行)
  → /api/report(报告) / /api/export(CSV导出)
```

### 对话
```
前端 /api/agent → agent.run(task, history) → route(关键词+LLM)
  → 套件模块 → 结构化结果 → 前端友好显示
```

## 5. 扩展新能力

1. 在 registry.py 用 `@capability(name, suite, desc)` 注册
2. 在 agent.py 的 INTENTS 加意图关键词（+LLM 意图识别）
3. 实现 handler（Domain 层模块）
4. 前端工作区 + API 端点（如需 Web 暴露）

## 5.1 原子化封装（fde 域 → 原子壳）

同一套核心模块可再加一层薄壳，暴露为可独立运行、可被组装的开源原子
（对齐生态原子化规范 `_os/plugin-agent-architecture.md`）。**不改核心，只加壳**：

| 域（原子 agent.type） | 原子名 | 现有核心模块（零改动） | 暴露能力 |
|---|---|---|---|
| `fde` | `solo-fde` | `agent.py` / `cli.py` / `cli_handlers.py` / `factory/*`（D0-D4 流程工具箱） | `fde.flow` `fde.ontology` `fde.data` |
| `memory` | `solo-memory` | `memory.py`（+ OptMem） | `memory.save` `memory.recall` |
| `monitor` | `solo-monitor` | `factory/monitor.py`（指标存储/告警引擎/工单状态机/MQTT/AI问数） | `monitor.metric` `monitor.alert` `monitor.ask` |
| `write` | `zh-write` | `writing.py`（与 zh-writing-checker 收敛为单一来源） | `write.check` `write.rewrite` |
| `codereview` | `code-review` | `code_review.py` / `code.py`（与 codeagent-minimal 收敛） | `codereview.review` `codereview.test` |

封装要点：
- 每原子 = 一个目录 + `manifest.json`（声明 `agent/name/version/open_source/provides/depends_on`）+ `main.py`（`AtomicAgent` 子类，`import` 并调用既有模块，包 `{ok, data/error}` 信封）。
- **开源原子只依赖同为开源的原子**，不反向依赖闭源（边界铁律，manifest 加载即强校验）。
- `main.py` 提供 `if __name__ == '__main__'` 独立自测入口，保证「可独立运行（A3）」。
- 原子可作为一个节点进入任意组装图（如「FDE + monitor + decision」构成现场运营链），也可按需拆成子原子复用。

## 6. 数据持久化

- 记忆：`~/.solo/memory/`（profile.json/facts.json/scenarios/sessions）
- 技能：`~/.solo/skills/index.json`
- 任务：`~/.solo/tasks/*.json`
- 配置：`~/.solo/provider.yaml`
- 全部原子写 + 并发锁，崩溃不损坏
