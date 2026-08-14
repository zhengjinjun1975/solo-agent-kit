# -*- coding: utf-8 -*-
"""web_api.py — solo-agent-kit Web 后端业务辅助层（零依赖，可独立测试）。

P0-2 收敛后保留：web_server.py 仍调用的路径/数据辅助函数
（safe_path / data_path / load_rows / guess_col_type / write_config）。
原 handle_memory_search / handle_stats / handle_ontology / setup_checks /
deploy / build_report 已被 app.py 门面覆盖，已删除。
"""
from __future__ import annotations

import os

from solo.factory import clean as clean_mod

# ---- 路径/数据辅助（供 web_server 调用，纯业务） ----

def safe_path(p: str) -> str:
    """路径参数白名单：只允许项目内路径（默认本地部署，防任意文件读）。

    项目根 = web_api.py 所在仓库根。绝对路径或超出项目根 → 返回 ""（调用方报错）。
    """
    if not p:
        return ""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
    p = p.replace("\\", "/")
    if os.path.isabs(p):
        full = p
    else:
        full = os.path.join(root, p)
    full = os.path.normpath(full)
    if full.startswith(os.path.normpath(root)):
        return full
    return ""


def data_path(p: str) -> str:
    """数据文件路径白名单：放开到硬盘，但只允许数据文件扩展名。

    供硬盘级浏览后的数据读取（csv/db/sqlite/xlsx），拒绝任意文件读取。
    """
    if not p:
        return ""
    ALLOWED = (".csv", ".db", ".sqlite", ".xlsx")
    p = os.path.normpath(p.replace("\\", "/"))
    if os.path.isabs(p) and os.path.exists(p) and p.lower().endswith(ALLOWED):
        return p
    return ""


def load_rows(body: dict) -> list:
    """从请求体解析数据源并读取为行列表。"""
    from solo import data_connector as dc
    from solo.base import DataSourceError
    if "source" in body:
        src = dict(body["source"])
        if "path" in src:
            src["path"] = data_path(src["path"]) or safe_path(src["path"])
        return dc.connect(src)
    if body.get("csvs"):
        merged = []
        for cp in body["csvs"][:10]:
            p = data_path(cp) or safe_path(cp)
            if not p:
                continue
            stype = "xlsx" if p.lower().endswith(".xlsx") else "csv"
            try:
                merged.extend(dc.connect({"type": stype, "path": p}))
            except DataSourceError:
                continue
        return merged
    if body.get("csv"):
        p = data_path(body["csv"]) or safe_path(body["csv"])
        stype = "xlsx" if p.lower().endswith(".xlsx") else "csv"
        return dc.connect({"type": stype, "path": p}) if p else []
    if body.get("db"):
        p = data_path(body["db"]) or safe_path(body["db"])
        if body.get("table"):
            return dc.connect({"type": "sqlite", "path": p, "table": body["table"]}) if p else []
        if body.get("query"):
            return dc.connect({"type": "sql", "path": p, "query": body["query"]}) if p else []
    return []


def guess_col_type(vals: list) -> str:
    """推断列类型（复用 clean 的逻辑）。"""
    if not vals:
        return "empty"
    return clean_mod.guess_type(str(vals[0]))


def write_config(config: dict) -> bool:
    """写 provider.yaml（极简 YAML 序列化）。"""
    path = os.path.join(os.path.expanduser("~"), ".solo", "provider.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        lines = ["# solo-agent-kit 模型配置", "provider:"]
        for tier, meta in config.get("provider", {}).items():
            lines.append(f"  {tier}:")
            for k, v in meta.items():
                lines.append(f"    {k}: {v}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception:
        return False
