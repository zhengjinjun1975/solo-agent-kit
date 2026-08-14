# -*- coding: utf-8 -*-
"""solo.factory — 工厂现场套件（与个人套件分离）。

给工厂级 FDE 的现场数据处理套件：数据审视 / 建模 / 需求验收 / 现场运维 / 图件。
零依赖，标准库实现。

    from solo.factory import data, ontology, survey, ops, diagram
    data.DataCleaner()         # 数据清洗（缺失/重复/异常值/类型）
    data.describe(...)         # 数据分析（描述/趋势/异常/SPC控制图）
    data.report(...)           # 数据审计（盘点/字典/质量/一键报告）
    ontology.Ontology()        # 本体建模（设备/工单 → 实体关系本体）
    survey.Survey(...)         # 需求→验收生命周期
    ops.Site()                 # 现场运维（台账/SSH 远程/资源监控）
    diagram.er_diagram(ont)    # 图件（ER/流程图/状态图，纯展示）

与 solo/ 根（个人套件：memory/skill/writing）解耦，可独立使用。
"""
from solo.factory import data  # noqa: F401
from solo.factory import ontology  # noqa: F401
from solo.factory import survey  # noqa: F401
from solo.factory import ops  # noqa: F401
from solo.factory import diagram  # noqa: F401
