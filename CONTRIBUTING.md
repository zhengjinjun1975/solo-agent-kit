# Contributing

欢迎提 issue 和 PR。

## Bug 报告
- 附复现命令（数据 + 问题 + 期望/实际输出）
- 标注环境（Python 版本 / 是否用本地 Ollama）

## PR 要求
- 代码 + 对应测试；跑通 `python -m pytest tests`（37 项：18 单测 + 19 e2e）
- 涉及问答/写作/记忆能力改动，附复现结果
- 示例数据一律用虚构数据，仓库不接收任何真实企业数据
- 保持标准库零依赖：新功能优先用 Python 标准库，不引入第三方依赖
- 方法论借鉴需在 NOTICE 声明（哪怕只借鉴机制，MIT/Apache 也要求署名）
- 遵守原子化边界：本仓库作为 fde 域开源原子（fde/memory/monitor/write），**不得引入对闭源组件的依赖**；为封装/组装而改核心的需求先进 TODO，不进开源壳层

## 提交规范
- 提交信息：`feat:` / `fix:` / `chore:` / `docs:` 前缀 + 简述
- 版本号：小版本递增（+0.01），改 `__version__` / README 徽标 / pyproject / CHANGELOG 四处保持一致
