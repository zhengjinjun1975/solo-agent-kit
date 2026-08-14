# -*- coding: utf-8 -*-
"""solo.factory — 工厂现场套件（与个人套件分离）。

给工厂级 FDE 的现场数据处理三件套：清洗 / 分析 / 建模。
零依赖，标准库实现。

    from solo.factory import clean, stats, ontology
    clean.DataCleaner()      # 数据清洗（缺失/重复/异常值/类型）
    stats.describe(...)      # 数据分析（描述/趋势/异常/SPC控制图）
    ontology.Ontology()      # 本体建模（设备/工单 → 实体关系本体）

与 solo/ 根（个人套件：memory/skill/writing/gen）解耦，可独立使用。
"""
from solo.factory import clean  # noqa: F401
from solo.factory import stats  # noqa: F401
from solo.factory import ontology  # noqa: F401
from solo.factory import survey  # noqa: F401
