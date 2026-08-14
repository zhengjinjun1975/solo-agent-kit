# -*- coding: utf-8 -*-
"""ontology — 工厂级本体建模（本体优先的差异化核心），按职责拆分后的包。

方法论（ibl.ai Ontology vs RAG + factory-ontology）：
RAG 检索文本，本体检索知识。工厂级本体建模的关键是**实体关系建模**——
不是"CSV→属性"（那是 DatatypeProperty），而是声明哪些列是**对象属性**
（外键引用其他实体 → ObjectProperty + target_class），生成可导航的实体图。

零依赖，标准库实现。复刻自 factory-ontology-kit 的 csv_to_owl（方法论借鉴）。

能力：
- from_csv: 单表→实体（数据属性）
- add_relations: 声明对象属性（外键→目标实体）
- build: 多实体 + 关系 → 完整本体
- query: 关系查询（实体间导航：某设备属于哪条产线/位于哪个位置）
- search: 语义检索

拆分：原单文件 ontology.py(561行) 按职责拆到子模块：
    core.py       状态底座（entities/triples/relations/col_cn）
    _naming.py    NS / guess_type / local_name 模块级工具
    build.py      from_csv / from_rows / build（建模）
    query.py      query / neighbors（关系查询）
    answer.py     answer / 聚合问答（计数/极值/枚举/列表，拆 4 个子方法降复杂度）
    output.py     to_nt / to_dict / entity_summary
    retrieve.py   search（检索）
    persist.py    save / load（JSON 持久化）
    enterprise.py from_schema / validate / traverse / _build_graph（企业级建模）

对外保持兼容：`from solo.factory.ontology import Ontology, NS, guess_type, local_name`。
"""
from __future__ import annotations

from ._naming import NS, guess_type, local_name  # noqa: F401
from .core import _Core  # noqa: F401
from .build import _BuildMixin  # noqa: F401
from .query import _QueryMixin  # noqa: F401
from .answer import _AnswerMixin  # noqa: F401
from .output import _OutputMixin  # noqa: F401
from .retrieve import _RetrieveMixin  # noqa: F401
from .persist import _PersistMixin  # noqa: F401
from .enterprise import _EnterpriseMixin  # noqa: F401


class Ontology(_Core, _BuildMixin, _QueryMixin, _AnswerMixin, _OutputMixin,
               _RetrieveMixin, _PersistMixin, _EnterpriseMixin):
    """工厂级本体：多实体 + 关系建模 + 查询。零依赖，JSON 持久化。

    数据模型：
        entities: {实体名: {cols, types, obj_props, instances}}
        obj_props: {列名: {rel, target_class, label}}  # 对象属性（外键）
        triples:   [(subj, pred, obj)]                  # 全部三元组
        relations: {实体名: {列: {target_class, label}}} # 关系索引（导航用）
    """
