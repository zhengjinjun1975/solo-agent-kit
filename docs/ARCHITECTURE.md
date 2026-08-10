# SoloAgentKit 架构文档

> 针对 FDE（工厂部署工程师）/一人公司的轻量全栈 AI 工具。零第三方依赖（纯标准库）。
> 本文档面向工程师：模块分层、契约、数据流、扩展方式。

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

## 6. 数据持久化

- 记忆：`~/.solo/memory/`（profile.json/facts.json/scenarios/sessions）
- 技能：`~/.solo/skills/index.json`
- 任务：`~/.solo/tasks/*.json`
- 配置：`~/.solo/provider.yaml`
- 全部原子写 + 并发锁，崩溃不损坏
