# -*- coding: utf-8 -*-
"""cli_handlers.py — CLI 命令的实质处理函数（按职责从 cli.py 拆出）。

cli.py 只保留：argparse 注册（_build_parser，命令名须留在 cli.py 供注册回归断言）
+ 查表分发（_HANDLERS）。本模块承载各命令的实际业务处理，并仍把重逻辑下沉
到 solo/app.py 与 solo/factory（薄壳化原则）。
"""
import os

from solo import memory as memory_mod
from solo import app as app_mod


def load_rows_csv(csv_path):
    import csv
    with open(csv_path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _now():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


# ─── 备份/恢复 ───
def backup(dest: str = None) -> dict:
    """P2-3: 备份记忆/技能/任务数据。"""
    import shutil
    import datetime
    home = os.path.expanduser("~")
    src_dirs = {"memory": os.path.join(home, ".solo", "memory"),
                "skills": os.path.join(home, ".solo", "skills"),
                "tasks": os.path.join(home, ".solo", "tasks")}
    dest_dir = dest or os.path.join(home, ".solo", "backups",
                                    datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    copied = {}
    for name, src in src_dirs.items():
        if os.path.exists(src):
            shutil.copytree(src, os.path.join(dest_dir, name), dirs_exist_ok=True)
            copied[name] = True
    return {"backup_dir": dest_dir, "copied": list(copied.keys())}


def restore(src: str) -> dict:
    """P2-3: 从备份目录恢复。"""
    import shutil
    home = os.path.expanduser("~")
    if not os.path.exists(src):
        return {"error": f"备份目录不存在: {src}"}
    targets = {"memory": os.path.join(home, ".solo", "memory"),
               "skills": os.path.join(home, ".solo", "skills"),
               "tasks": os.path.join(home, ".solo", "tasks")}
    restored = []
    for name, tgt in targets.items():
        bsrc = os.path.join(src, name)
        if os.path.exists(bsrc):
            shutil.copytree(bsrc, tgt, dirs_exist_ok=True)
            restored.append(name)
    return {"restored": restored, "from": src}


# ─── 交付辅助（FDE D0/D1/D4）───
def assist_draft_questions(args):
    """起草问题集(FDE D0)。行业联动：--industry 决定默认实体/量词/列名中文映射。"""
    from solo.factory.assist import draft_questions
    rows = load_rows_csv(args.csv)
    qs = draft_questions(rows, args.entity, limit=args.limit, industry=getattr(args, "industry", None))
    ind = getattr(args, "industry", None)
    out = {"questions": qs, "count": len(qs)}
    if ind:
        from solo.factory.industry import apply_industry
        out["industry"] = apply_industry(ind)
    return out


def assist_lexicon_draft(args):
    """起草词典初稿(FDE D1)。行业联动：--industry 决定列名中文映射。"""
    from solo.factory.assist import lexicon_draft
    rows = load_rows_csv(args.csv)
    headers = list(rows[0].keys()) if rows else []
    ind = getattr(args, "industry", None)
    lex = lexicon_draft(headers, rows[:30], industry=ind)
    if args.json:
        out = lex
    else:
        out = {"columns": len(lex), "draft": lex}
    if ind:
        from solo.factory.industry import apply_industry
        out["industry"] = apply_industry(ind)
    return out


def assist_report_draft(args):
    """起草交付报告(FDE D4)。--json 输出结构化 dict(对齐闭源 deliver, 供闭源消费)。"""
    from solo.factory.assist import report_draft, report_draft_dict
    ind = getattr(args, "industry", None)
    if getattr(args, "json", False):
        return report_draft_dict(kb=args.kb, industry=ind, hit=args.hit,
                                 questions_n=args.questions, hits=args.hits,
                                 asset_versions=args.asset_versions)
    md, ai = report_draft(kb=args.kb, industry=ind, hit=args.hit,
                          questions_n=args.questions, hits=args.hits,
                          asset_versions=args.asset_versions, note=args.note)
    out = {"report": md}
    if ai and ai.get("ok"):
        out["ai_taste"] = {"score": ai["ai_score"], "note": ai["note"],
                           "verdict": ai.get("verdict"),
                           "suggestions": ai["suggestions"][:6],
                           "hard_fails": ai["hard_fails"]}
    return out


def assist_to_factory_lexicon(args):
    """词典初稿 → 工厂本体 lexicon 契约（FDE D1 下游，独立 CLI 入口）。"""
    from solo.factory.assist import lexicon_draft, to_factory_lexicon
    rows = load_rows_csv(args.csv)
    headers = list(rows[0].keys()) if rows else []
    d = lexicon_draft(headers, rows[:30], industry=getattr(args, "industry", None))
    return to_factory_lexicon(d, table_name=args.table_name, entity_cn=args.entity_cn,
                              industry=getattr(args, "industry", None))


def assist_to_review_items(args):
    """词典初稿 → 闭源 review 待确认队列（P2 接线入口）。"""
    from solo.factory.assist import lexicon_draft, to_review_items
    rows = load_rows_csv(args.csv)
    headers = list(rows[0].keys()) if rows else []
    d = lexicon_draft(headers, rows[:30], industry=getattr(args, "industry", None))
    items = to_review_items(d)
    return {"items": items, "count": len(items)}


# ─── 行业联动 ───
def industry_list():
    """列出已登记行业(行业→kb/词典联动注册表)。"""
    from solo.factory.industry import industries_list
    return {"industries": industries_list(), "count": len(industries_list())}


def industry_set(args):
    """改行业事件驱动：设置当前行业 + 自动重建 FDE 产物（问题集/词典/报告/决策）。"""
    from solo.factory.industry import rebuild_industry_artifacts
    rows = None
    if args.csv:
        rows = load_rows_csv(args.csv)
    return rebuild_industry_artifacts(
        industry=args.industry or None,
        rows=rows,
        out_dir=(args.out_dir or None),
        questions_n=args.limit)


def industry_current():
    """查看当前行业及生效配置（改行业自动联动状态）。"""
    from solo.factory.industry import apply_industry, get_current_industry
    return {"current": get_current_industry() or "(默认工厂)", "apply": apply_industry()}


# ─── 本体命令 ───
def onto_build(args):
    """从 CSV 建本体（onto-to-nt/answer/search 共用）。返回 (Ontology, 错误dict)。

    注入行业 col_cn（--industry）使聚合问答能答行业化列名（与 draft_questions 措辞一致）；
    未显式给 --entity 时，缺省取行业实体中文名（如 阀门），保证计数题 "有多少个阀门" 可答。
    """
    from solo.factory.ontology import Ontology
    col_cn = {}
    entity = getattr(args, "entity", None)
    ind = getattr(args, "industry", None)
    if ind:
        from solo.factory import industry as ind_mod
        cfg = ind_mod.load_industry(ind)
        col_cn = dict(cfg.get("col_cn") or {})
        if not entity and cfg.get("entity_cn"):
            entity = cfg["entity_cn"]
    rows = load_rows_csv(args.csv)
    if not rows:
        return None, {"error": "数据源无效或为空"}
    o = Ontology(col_cn=col_cn)
    o.from_rows(rows, entity_name=entity, id_col=args.id_col)
    o.build()
    return o, None


def onto_to_nt(args):
    """CSV → 本体 → N-Triples（消除 Python-only 无入口断层）。"""
    o, err = onto_build(args)
    if err:
        return err
    return {"nt": o.to_nt(), "entities": list(o.entities.keys()),
            "triples": len(o.triples)}


def onto_answer(args):
    """本体聚合问答（计数/极值/枚举/列表，闭环 draft_questions 生成题）。"""
    o, err = onto_build(args)
    if err:
        return err
    return {"question": args.question, "answers": o.answer(args.question, entity=args.entity)}


def onto_search(args):
    """本体三元组检索。"""
    o, err = onto_build(args)
    if err:
        return err
    return {"term": args.term, "hits": o.search(args.term, top_k=args.top_k)}
