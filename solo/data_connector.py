# -*- coding: utf-8 -*-
"""data_connector.py — 数据源接入（CSV / SQLite / 数据库统一读取）。

方法论：数据类模块（清洗/分析/建模）应从多种数据源接入——
文件（CSV）或数据库（SQLite，未来 MySQL/Postgres）。统一为行列表。

P0 修复：不再静默返回 []，用 DataSourceError 透传原因；SQL 仅允许 SELECT。
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3

from solo.base import DataSourceError, get_logger

log = get_logger(__name__)


def connect(source: dict) -> list:
    """从数据源读取为行列表(list[dict])。

    source:
      {"type":"csv", "path":"..."}             CSV 文件
      {"type":"sqlite", "path":"...", "table":"..."}   SQLite 表
      {"type":"sql", "path":"...", "query":"..."}    只读 SQL 查询
    失败抛 DataSourceError（区分原因，不再静默返回 []）。
    """
    stype = source.get("type", "csv")
    try:
        if stype == "csv":
            return _read_csv(source.get("path", ""))
        if stype == "sqlite":
            return _read_sqlite(source.get("path", ""), source.get("table", ""))
        if stype == "sql":
            return _read_sql(source)
        raise DataSourceError(f"未知数据源类型: {stype}")
    except DataSourceError:
        raise
    except Exception as e:
        log.warning("数据源读取失败 %s: %s", source, e)
        raise DataSourceError("数据源读取失败", str(e))


def list_tables(db_path: str) -> list:
    """列出 SQLite 数据库的所有表名。失败返回 []（表列表非关键）。"""
    if not db_path or not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        conn.close()
        return tables
    except Exception as e:
        log.warning("列出表失败 %s: %s", db_path, e)
        return []


def _read_csv(path: str) -> list:
    if not path or not os.path.exists(path):
        raise DataSourceError(f"CSV 文件不存在: {path}")
    try:
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except Exception as e:
        log.warning("CSV 读取失败 %s: %s", path, e)
        raise DataSourceError(f"CSV 读取失败: {path}", str(e))


def _read_sqlite(path: str, table: str) -> list:
    if not path or not os.path.exists(path):
        raise DataSourceError(f"数据库文件不存在: {path}")
    if not table:
        raise DataSourceError("未指定数据库表")
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM \"{table}\" LIMIT 5000")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log.warning("SQLite 读取失败 %s.%s: %s", path, table, e)
        raise DataSourceError(f"数据库表读取失败: {table}", str(e))


# 只读 SQL 白名单（P0-4）：仅允许 SELECT 查询
_SQL_SELECT_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_SQL_DANGEROUS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|PRAGMA)\b", re.IGNORECASE)


def _read_sql(source: dict) -> list:
    """只读 SQL 查询（仅允许 SELECT，拒绝写/危险操作）。"""
    db_path = source.get("path", "")
    query = source.get("query", "")
    if not db_path or not os.path.exists(db_path):
        raise DataSourceError(f"数据库文件不存在: {db_path}")
    if not query:
        raise DataSourceError("未指定 SQL 查询")
    if not _SQL_SELECT_RE.match(query):
        raise DataSourceError("仅允许 SELECT 只读查询")
    if _SQL_DANGEROUS_RE.search(query):
        raise DataSourceError("检测到危险 SQL 操作，已拒绝")
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query)
        rows = [dict(r) for r in cur.fetchall()[:5000]]
        conn.close()
        return rows
    except Exception as e:
        log.warning("SQL 查询失败 %s: %s", db_path, e)
        raise DataSourceError("SQL 查询失败", str(e))
