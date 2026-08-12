# FDE 套件运行手册（solo-agent-kit）

> 用途：FDE 个人交付辅助工具。干"起草/记忆/方法论"的辅助活，不碰算法和交付系统核心。
> 角色：solo 辅助人（FDE）、开源管算法、闭源管交付。
> 版本：v0.5.0

## 一、能力边界（solo 只做辅助）

| 能干什么 | 不能干什么 |
|:--|:--|
| 起草问题集（D0）| 不碰核心算法（本体/检索在开源）|
| 生成词典初稿（D1）| 不碰交付编排（在闭源）|
| 起草交付报告（D4）| 不管理甲方数据（在闭源）|
| 记忆/写作/方法论沉淀 | — |

## 二、核心辅助能力

### 1. 问题集起草（D0，benchmark 候选题）
```python
from solo.factory.assist import draft_questions
qs = draft_questions(rows, "设备")
# → ['有多少台设备', 'device_type有哪些', '最大的power_kw', ...]
```

### 2. 词典初稿（D1，供闭源 lexicon_agent / 人在环）
```python
from solo.factory.assist import lexicon_draft
lex = lexicon_draft(headers, sample_rows)
# → {列: {cn, type, enum, suggest}}（枚举/数值/文本建议）
```

### 3. 交付报告起草（D4，初稿供闭源 deliver）
```python
from solo.factory.assist import report_draft
rep = report_draft(kb='valve', industry='阀门制造', hit=0.8,
                   questions_n=5, hits=4, asset_versions=2)
```

### 4. 本体辅助（建模/问答/检索）
```python
from solo.factory.ontology import Ontology
o = Ontology()
o.from_csv('data.csv', entity_name='设备')
o.answer('所在车间', entity='设备')   # 结构化本体问答
o.to_nt('output.nt')                # 导出本体（先 build()）
```

## 三、FDE 工作流中的介入点

```
D0 入场基线 → solo 起草问题集
D1 建模审查 → solo 生成词典初稿（人在环确认在闭源）
D2 验证补全 → solo 分析缺口/补词建议
D3 培训试运行 → solo 记录客户记忆
D4 交付 → solo 起草报告初稿
```

## 四、记忆（跨客户）
- 三层两域记忆：热域画像/温域事实+场景/冷域归档
- 换客户不丢项目上下文
- `solo init` 初始化记忆库

## 五、写作/方法论
- 公众号/文档/方法论输出
- 踩过的坑/验证流程 → skill 沉淀复用

## 六、常见操作
```bash
python examples/example_04_factory_ontology.py  # 工厂本体建模示例
python examples/example_06_factory_data.py      # 工厂数据示例
```

## 七、故障排查
| 问题 | 处理 |
|:--|:--|
| to_nt 对象属性误导出 | 先 o.build() 再导出 |
| 列中文名不翻译 | 词典初稿保留英文，人在环补中文 |
| 问题集重复 | FDE 挑选/去重后进闭源 benchmark |
