# Changelog

所有显著变更记录在此。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.1.0] - 2026-08-10

### 新增
- 项目骨架：pyproject.toml（零第三方依赖）、README、LICENSE(Apache-2.0)、NOTICE
- `solo/` 包：本体优先方法论 Agent 的最小闭环
  - `provider.py`：模型分层抽象（本地 ornith / 远端 DeepSeek / 嵌入 nomic），
    分级退出码（0-5），云端无 key 明确报错
  - `memory.py`：三层两域记忆（热域画像/温域事实+场景/冷域会话），
    Obsidian Markdown 导入导出，零依赖
  - `cli.py`：solo init/run/skill-add/import-obsidian/export-markdown/version
- `provider.yaml.example`：模型配置模板（key 从环境变量读，不入仓库）

### 方法论
- VISION.md：40 章节完整蓝图（本体优先 + 三层两域 + harness 工程 + 竞品定位）
- 差异化：本体优先（ibl.ai 证实 RAG 缺失层）；轻 ≠ 不行（工程极简非能力阉割）
