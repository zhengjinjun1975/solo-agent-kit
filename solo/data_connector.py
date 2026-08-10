# -*- coding: utf-8 -*-
"""data_connector.py — 数据源接入（CSV / SQLite / 数据库统一读取）。

方法论：数据类模块（清洗/分析/建模）应从多种数据源接入——
文件（CSV）或数据库（SQLite，未来 MySQL/Postgres）。统一为行列表。

零依赖：CSV 用标准库 csv；SQLite 用标准库 sqlite3。
"""
from __future__ import annotations

import csv
import os
import sqlite3


def connect(source: dict) -> list:
    """从数据源读取为行列表(list[dict])。

    source:
      {"type":"csv", "path":"..."}             CSV 文件
      {"type":"sqlite", "path":"...", "table":"..."}   SQLite 表
    返回 [] 若数据源无效。
    """
    stype = source.get("type", "csv")
    if stype == "csv":
        return _read_csv(source.get("path", ""))
    if stype == "sqlite":
        return _read_sqlite(source.get("path", ""), source.get("table", ""))
    if stype == "sql":
        return _read_sql(source)
    return []


def list_tables(db_path: str) -> list:
    """列出 SQLite 数据库的所有表名。"""
    if not db_path or not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        conn.close()
        return tables
    except Exception:
        return []


def _read_csv(path: str) -> list:
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _read_sqlite(path: str, table: str) -> list:
    if not path or not os.path.exists(path) or not table:
        return []
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM \"{table}\" LIMIT 1000")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def _read_sql(source: dict) -> list:
    """通用 SQL 查询（通过 sqlite3，未来扩展其他驱动）。"""
    db_path = source.get("path", "")
    query = source.get("query", "")
    if not db_path or not os.path.exists(db_path) or not query:
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query)
        rows = [dict(r) for r in cur.fetchall()[:1000]]
        conn.close()
        return rows
    except Exception:
        return []
