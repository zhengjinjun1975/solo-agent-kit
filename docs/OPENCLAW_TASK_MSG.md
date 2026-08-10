你是 OpenClaw，三体架构的意识中枢/总编辑。请对以下项目执行一次完整的工程审查，输出设计审查 + 代码审查 + 测试 + 方法论缺口补齐 + 优化方案。

【项目】solo-agent-kit v0.5.0
【定位】针对 FDE（工厂/前置部署工程师）的轻量化全栈 AI 工具，一人公司的必备能力。本体优先 + 双套件（个人 solo/ + 工厂 solo/factory/）+ 记忆/写作/代码/数据/建模 + 零依赖（核心 1586 行）。
【仓库】E:\open-source\solo-agent-kit （远程 github.com/zhengjinjun1975/solo-agent-kit）

【请依次完成】

1. 完整测试
- 跑 tests/test_core.py 全部 18 项 pytest
- 跑端到端 CLI：solo setup / run / skill-add / factory-clean / factory-stats / factory-onto / import-obsidian / export-markdown / config
- 验证 Web 后端 solo/web_server.py 核心端点（起服务后测 /api/agent 的意图路由 + /api/capabilities + /api/config）
- 报告每项结果（通过/失败/异常）

2. 代码审查（逐文件）
- solo/*.py + solo/factory/*.py + solo/web_server.py + web/index.html
- 已知遗留：CodeAgent 静态审查报 33 问题（13 major 圈复杂度 + 20 minor 未用import误报）
  - major：clean(24)/code.index(20)/scan(14) 圈复杂度高
  - minor：`from __future__ import annotations` 报未使用（Python延迟注解，误报）
  - 请区分：必须改 / 建议改 / 可接受（反过度工程）
- 找真实 bug（未处理异常/逻辑漏洞/安全风险，如 web_server 路径穿越、xss）

3. 设计审查
- 双套件分离是否合理？边界清晰吗？
- AI 原生对话路由（agent.py 意图识别）设计完备吗？意图覆盖够吗？该不该升 v2 LLM 意图？
- provider.yaml 模型分层 + 降级兜底符合"轻≠不行"吗？
- 前端 AI 原生对话中心 + 浅色护眼配色符合工程化落地吗？

4. 方法论目标缺口
对照 VISION.md 蓝图（40+章），列出：哪些蓝图承诺已落地、哪些未落地（反过度工程该不该补）、哪些该砍（过度设计）。重点看：harness自进化(AHE论文)该不该开始？记忆语义检索该不该换sqlite-vec？

5. 输出格式
- 完整测试结果表
- 代码审查报告（按严重度分级）
- 设计审查结论
- 方法论缺口清单
- 优化方案（按优先级 P0/P1/P2）

【输出要求】用中文，结构化（表格/清单），每项给明确结论（通过/建议/拒绝）和理由。这是给技术负责人看的工作报告，务实不虚夸。审查材料在仓库内（VISION.md 是蓝图，docs/OPENCLAW_REVIEW_BRIEF.md 是委托简报，可参考）。