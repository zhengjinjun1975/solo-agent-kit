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
      {"type":"xlsx", "path":"..."}            Excel 文件
    失败抛 DataSourceError（区分原因，不再静默返回 []）。
    limit/offset 支持分页（大表友好）。
    """
    stype = source.get("type", "csv")
    limit = source.get("limit")
    offset = source.get("offset", 0)
    try:
        if stype == "csv":
            return _read_csv(source.get("path", ""))
        if stype == "sqlite":
            return _read_sqlite(source.get("path", ""), source.get("table", ""), limit, offset)
        if stype == "sql":
            return _read_sql(source)
        if stype == "xlsx":
            return _read_xlsx(source.get("path", ""))
        if stype in ("mysql", "postgres"):
            return _read_rdbms(source, limit, offset)
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


def iter_csv(path: str):
    """P2-5: 流式读取 CSV——逐行 yield dict，不整文件入内存（大文件友好）。"""
    if not path or not os.path.exists(path):
        raise DataSourceError(f"CSV 文件不存在: {path}")
    try:
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield row
    except Exception as e:
        log.warning("CSV 流式读取失败 %s: %s", path, e)
        raise DataSourceError(f"CSV 读取失败: {path}", str(e))


def _read_csv(path: str) -> list:
    if not path or not os.path.exists(path):
        raise DataSourceError(f"CSV 文件不存在: {path}")
    try:
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except Exception as e:
        log.warning("CSV 读取失败 %s: %s", path, e)
        raise DataSourceError(f"CSV 读取失败: {path}", str(e))


def _read_xlsx(path: str) -> list:
    """P2-4: 读取 xlsx（标准库 zipfile+xml 解析，零依赖）。

    支持单 sheet 的 xlsx，返回 list[dict]（首行为表头）。
    """
    if not path or not os.path.exists(path):
        raise DataSourceError(f"xlsx 文件不存在: {path}")
    import zipfile
    from xml.etree import ElementTree as ET
    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        with zipfile.ZipFile(path) as z:
            # 找第一个 sheet
            sheet_name = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
            if not sheet_name:
                raise DataSourceError("xlsx 无工作表")
            root = ET.fromstring(z.read(sheet_name[0]))
        rows = []
        for row in root.iter(f"{NS}row"):
            cells = {}
            for c in row.iter(f"{NS}c"):
                ref = c.get("r", "")
                col = "".join(ch for ch in ref if ch.isalpha())
                v = c.find(f"{NS}v")
                val = v.text if v is not None else ""
                cells[col] = val
            rows.append(cells)
        if not rows:
            return []
        # 首行做表头，后续行映射为 dict
        header = rows[0]
        cols = list(header.keys())
        out = []
        for r in rows[1:]:
            out.append({header.get(c, c): r.get(c, "") for c in cols})
        return out
    except DataSourceError:
        raise
    except Exception as e:
        log.warning("xlsx 读取失败 %s: %s", path, e)
        raise DataSourceError(f"xlsx 读取失败: {path}", str(e))


def _safe_table_name(table: str) -> str:
    """表名白名单校验: 仅允许字母/下划线开头, 后跟字母数字下划线。

    防 SQL 注入: 表名直接拼进 SELECT FROM, 若含特殊字符(引号/分号/空格)可注入。
    返回清洗后的表名; 非法则抛 DataSourceError。
    """
    if not table:
        raise DataSourceError("未指定数据库表")
    t = str(table).strip('`" ')
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t):
        raise DataSourceError(f"非法表名: {table}")
    return t


def _read_sqlite(path: str, table: str, limit: int = None, offset: int = 0) -> list:
    if not path or not os.path.exists(path):
        raise DataSourceError(f"数据库文件不存在: {path}")
    if not table:
        raise DataSourceError("未指定数据库表")
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # P2-5: 分页读取（limit/offset），大表不一次全读
        lim = limit or 5000
        # 表名白名单校验(防注入), limit/offset 已 int() 强制
        safe_table = _safe_table_name(table)
        cur.execute(f"SELECT * FROM \"{safe_table}\" LIMIT {int(lim)} OFFSET {int(offset)}")
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


def _read_rdbms(source: dict, limit: int = None, offset: int = 0) -> list:
    """读取 MySQL / PostgreSQL 表（企业真实台账接入，可选驱动）。

    source:
      {"type":"mysql","host":"...","port":3306,"user":"...","password":"...","db":"...","table":"..."}
      {"type":"postgres","host":"...","port":5432,"user":"...","password":"...","db":"...","table":"..."}

    零依赖运行时：驱动未装时给出清晰安装提示，不破坏核心功能。
    """
    import importlib
    stype = source.get("type")
    host = source.get("host", "127.0.0.1")
    port = source.get("port", 3306 if stype == "mysql" else 5432)
    user = source.get("user", "")
    password = source.get("password", "")
    dbname = source.get("db", "")
    table = source.get("table", "")
    if not user or not dbname:
        raise DataSourceError(f"{stype} 需提供 user/db")
    if not table:
        raise DataSourceError(f"{stype} 需提供 table")
    try:
        if stype == "mysql":
            mod = importlib.import_module("pymysql")
            conn = mod.connect(host=host, port=port, user=user, password=password,
                               database=dbname, connect_timeout=8)
            cur = conn.cursor(mod.cursors.DictCursor)
        else:
            mod = importlib.import_module("psycopg2")
            conn = mod.connect(host=host, port=port, user=user, password=password,
                               dbname=dbname, connect_timeout=8)
            cur = conn.cursor()
        # 只读 + 分页
        # 表名白名单校验(防注入, 替代弱 replace), limit/offset 已 int() 强制
        safe_table = _safe_table_name(table)
        q = f"SELECT * FROM {safe_table}"
        if limit:
            q += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        cur.execute(q)
        if stype == "mysql":
            rows = [dict(r) for r in cur.fetchall()]
        else:
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close(); conn.close()
        return rows
    except ImportError as e:
        pkg = "pymysql" if stype == "mysql" else "psycopg2-binary"
        raise DataSourceError(f"{stype} 驱动未安装，请运行: pip install {pkg}（可选，不破坏零依赖运行时）")
    except DataSourceError:
        raise
    except Exception as e:
        log.warning("%s 读取失败 %s:%s/%s: %s", stype, host, port, table, e)
        raise DataSourceError(f"{stype} 读取失败", str(e))
