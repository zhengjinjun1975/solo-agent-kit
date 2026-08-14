# -*- coding: utf-8 -*-
"""cli.py — solo 命令入口（agent-first，JSON out + 分级退出码）。

薄壳化：只做 argparse 解析 + 一行调 app 门面（业务逻辑下沉 solo/app.py）。
命令：
    solo init                   初始化记忆库
    solo run "<任务>"            走方法论（记忆装载→推理→行动→记忆提交）
    solo skill-add "<经验>"      从任务提取可复用经验
    solo import-obsidian <dir>   导入 Obsidian 笔记为记忆
    solo export-markdown <dir>   导出记忆为 Markdown
    solo setup                   部署检查（环境/模型/初始化）
    solo config                  查看/校验 provider.yaml 配置
    solo factory-clean <csv>     工厂数据清洗
    solo factory-stats <csv>     工厂数据分析（描述/趋势/SPC）
    solo factory-onto <csv>      工厂本体建模
    solo version                 显示版本
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from solo import __version__
from solo import memory as memory_mod
from solo import provider as provider_mod
from solo import app as app_mod


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="solo", description="OPC 与工厂级 FDE 的方法论 Agent")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("version", help="显示版本")
    sub.add_parser("init", help="初始化记忆库")
    sub.add_parser("setup", help="部署检查（环境/模型/初始化）")
    sub.add_parser("config", help="查看/校验 provider.yaml 配置")

    p_run = sub.add_parser("run", help="运行一个任务（走完整方法论）")
    p_run.add_argument("task", help="任务描述")
    p_run.add_argument("--tier", choices=["auto", "local", "remote"], default="auto", help="模型分层")

    p_skill = sub.add_parser("skill-add", help="从任务提取可复用经验")
    p_skill.add_argument("exp", help="经验内容")

    p_imp = sub.add_parser("import-obsidian", help="导入 Obsidian 笔记")
    p_imp.add_argument("dir")
    p_exp = sub.add_parser("export-markdown", help="导出记忆为 Markdown")
    p_exp.add_argument("dir")

    # 工厂套件命令
    p_fc = sub.add_parser("factory-clean", help="工厂数据清洗")
    p_fc.add_argument("csv", help="CSV 数据文件")
    p_fc.add_argument("--method", choices=["drop", "zero", "mean"], default="drop", help="缺失值处理")
    p_fc.add_argument("--outlier", choices=["iqr", "zscore"], default="iqr", help="异常值方法")

    p_fs = sub.add_parser("factory-stats", help="工厂数据分析")
    p_fs.add_argument("csv", help="CSV 数据文件")
    p_fs.add_argument("--col", help="分析的数值列名")

    p_fo = sub.add_parser("factory-onto", help="工厂本体建模")
    p_fo.add_argument("csv", help="CSV 数据文件")
    p_fo.add_argument("--entity", help="实体名")
    p_fo.add_argument("--id", dest="id_col", help="主键列")
    p_fo.add_argument("--relations", help="关系声明 JSON 文件")

    # 交付辅助(FDE D0/D1/D4): 问题集/词典初稿/报告起草（行业→kb/词典联动）
    p_dq = sub.add_parser("draft-questions", help="起草问题集(FDE D0)")
    p_dq.add_argument("csv", help="CSV 数据文件")
    p_dq.add_argument("--entity", default=None, help="实体名(用于量词, 缺省时用行业默认实体/通用'设备')")
    p_dq.add_argument("--industry", help="行业名(联动实体/量词/列名中文映射)")
    p_dq.add_argument("--limit", type=int, default=12, help="问题数上限")
    p_ld = sub.add_parser("lexicon-draft", help="起草词典初稿(FDE D1)")
    p_ld.add_argument("csv", help="CSV 数据文件")
    p_ld.add_argument("--industry", help="行业名(联动列名中文映射/实体)")
    p_ld.add_argument("--json", action="store_true", help="输出 JSON")
    p_rd = sub.add_parser("report-draft", help="起草交付报告(FDE D4)")
    p_rd.add_argument("--kb", help="知识库名(缺省时按行业自动解析)")
    p_rd.add_argument("--industry", help="行业名")
    p_rd.add_argument("--hit", type=float, default=0.0, help="命中率0-1")
    p_rd.add_argument("--questions", type=int, default=0, help="题数")
    p_rd.add_argument("--hits", type=int, default=0, help="命中题数")
    p_rd.add_argument("--asset-versions", type=int, default=0, help="资产版本数")
    p_rd.add_argument("--note", default="", help="补充说明")
    p_rd.add_argument("--json", action="store_true", help="输出结构化 dict(对齐闭源 deliver 报告, 供 FDE D4 消费)")
    sub.add_parser("industry-list", help="列出已登记行业(行业→kb/词典联动注册表)")
    # 改行业事件驱动：设置当前行业 + 自动重建 FDE 产物（问题集/词典/报告/决策）
    p_iset = sub.add_parser("industry-set", help="设置当前行业并自动重建 FDE 产物(改行业事件驱动)")
    p_iset.add_argument("industry", nargs="?", default="", help="行业名(空 → 复位默认工厂)")
    p_iset.add_argument("csv", nargs="?", default="", help="数据 CSV(给出才重建问题集/词典)")
    p_iset.add_argument("--out-dir", default="", help="产物包持久化目录(默认不落盘)")
    p_iset.add_argument("--limit", type=int, default=12, help="问题集上限")
    sub.add_parser("industry-current", help="查看当前行业及生效配置(改行业自动联动状态)")

    # 任务状态控制面
    p_tn = sub.add_parser("task-new", help="新建任务")
    p_tn.add_argument("goal", help="任务目标")
    p_ts = sub.add_parser("task-status", help="查看任务状态")
    p_ts.add_argument("tid", nargs="?", help="任务id(缺省列出所有)")
    p_tg = sub.add_parser("task-gate", help="记录决策门")
    p_tg.add_argument("tid")
    p_tg.add_argument("question", help="待确认问题")
    p_tr = sub.add_parser("task-resolve", help="解决所有待确认门")
    p_tr.add_argument("tid")

    # 备份恢复（P2-3）
    p_bk = sub.add_parser("backup", help="备份记忆/技能/任务")
    p_bk.add_argument("dest", nargs="?", help="备份目录(默认 ~/.solo/backups)")
    p_rs = sub.add_parser("restore", help="恢复备份")
    p_rs.add_argument("src", help="备份目录")

    try:
        args = parser.parse_args(argv)
        result = _dispatch(args)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return provider_mod.EXIT_OK
    except SystemExit as e:
        # argparse 未知命令/参数错误 → 用户错误(1)，不与 EXIT_NETWORK(2) 撞车
        code = e.code if isinstance(e.code, int) and e.code not in (0, 2) else (provider_mod.EXIT_OK if e.code == 0 else provider_mod.EXIT_USER_ERR)
        return code
    except provider_mod.ProviderError as e:
        print(json.dumps({"error": str(e), "code": e.code}, ensure_ascii=False), file=sys.stderr)
        return e.code
    except Exception as e:
        print(json.dumps({"error": str(e), "code": provider_mod.EXIT_OTHER}, ensure_ascii=False), file=sys.stderr)
        return provider_mod.EXIT_OTHER


def _load_rows_csv(csv_path):
    import csv
    with open(csv_path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _dispatch(args):
    cmd = args.cmd
    if cmd == "version":
        return {"version": __version__}
    if cmd == "init":
        m = memory_mod.Memory()
        m.set_profile("created", _now())
        return {"init": True, "mem_dir": m.dir}
    if cmd == "setup":
        return app_mod.check_environment()
    if cmd == "config":
        return app_mod.config_view()
    if cmd == "import-obsidian":
        m = memory_mod.Memory()
        return {"imported": m.import_markdown(args.dir)}
    if cmd == "export-markdown":
        m = memory_mod.Memory()
        m.export_markdown(args.dir)
        return {"exported_to": args.dir}
    if cmd == "skill-add":
        m = memory_mod.Memory()
        return {"added": m.add_fact(args.exp, tags=["skill"])}
    if cmd == "run":
        from solo import agent as agent_mod
        return agent_mod.run(args.task, tier=args.tier)
    if cmd == "factory-clean":
        return app_mod.data_clean(_load_rows_csv(args.csv), method=args.method, outlier=args.outlier)
    if cmd == "factory-stats":
        return app_mod.data_stats(_load_rows_csv(args.csv), col=args.col)
    if cmd == "factory-onto":
        return app_mod.build_ontology(_load_rows_csv(args.csv), entity=args.entity,
                                      id_col=args.id_col, relations=args.relations)
    if cmd == "draft-questions":
        return _assist_draft_questions(args)
    if cmd == "lexicon-draft":
        return _assist_lexicon_draft(args)
    if cmd == "report-draft":
        return _assist_report_draft(args)
    if cmd == "industry-list":
        return _industry_list()
    if cmd == "industry-set":
        return _industry_set(args)
    if cmd == "industry-current":
        return _industry_current()
    if cmd == "task-new":
        from solo.task import Task
        t = Task()
        task = t.new(args.goal)
        return {"id": task["id"], "goal": task["goal"], "state": task["state"]}
    if cmd == "task-status":
        from solo.task import Task
        t = Task()
        if args.tid:
            return t.status(args.tid)
        return {"tasks": t.list()}
    if cmd == "task-gate":
        from solo.task import Task
        t = Task()
        return t.gate(args.tid, args.question)
    if cmd == "task-resolve":
        from solo.task import Task
        t = Task()
        return t.resolve(args.tid)
    if cmd == "backup":
        return _backup(args.dest)
    if cmd == "restore":
        return _restore(args.src)
    return {"error": "unknown command"}


def _backup(dest: str = None) -> dict:
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


def _restore(src: str) -> dict:
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


def _now():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def _assist_draft_questions(args):
    """起草问题集(FDE D0)。行业联动：--industry 决定默认实体/量词/列名中文映射。"""
    from solo.factory.assist import draft_questions
    rows = _load_rows_csv(args.csv)
    qs = draft_questions(rows, args.entity, limit=args.limit, industry=getattr(args, "industry", None))
    ind = getattr(args, "industry", None)
    out = {"questions": qs, "count": len(qs)}
    if ind:
        from solo.factory.industry import apply_industry
        out["industry"] = apply_industry(ind)
    return out


def _assist_lexicon_draft(args):
    """起草词典初稿(FDE D1)。行业联动：--industry 决定列名中文映射。"""
    from solo.factory.assist import lexicon_draft
    rows = _load_rows_csv(args.csv)
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


def _assist_report_draft(args):
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
                           "suggestions": ai["suggestions"][:6],
                           "hard_fails": ai["hard_fails"]}
    return out


def _industry_list():
    """列出已登记行业(行业→kb/词典联动注册表)。"""
    from solo.factory.industry import industries_list
    return {"industries": industries_list(), "count": len(industries_list())}


def _industry_set(args):
    """改行业事件驱动：设置当前行业 + 自动重建 FDE 产物（问题集/词典/报告/决策）。"""
    from solo.factory.industry import rebuild_industry_artifacts
    rows = None
    if args.csv:
        rows = _load_rows_csv(args.csv)
    return rebuild_industry_artifacts(
        industry=args.industry or None,
        rows=rows,
        out_dir=(args.out_dir or None),
        questions_n=args.limit)


def _industry_current():
    """查看当前行业及生效配置（改行业自动联动状态）。"""
    from solo.factory.industry import apply_industry, get_current_industry
    return {"current": get_current_industry() or "(默认工厂)", "apply": apply_industry()}


if __name__ == "__main__":
    sys.exit(main())
