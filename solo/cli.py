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
    solo survey-outline          需求访谈提纲（行业数据驱动）
    solo survey-structure <name> <story>  结构化一条需求（编号R-xxx）
    solo survey-srs <name>       生成SRS需求文档
    solo survey-acceptance <name>  生成验收清单+勾稽检查
    solo code-review <file>      代码审查（静态分析+0-100评分）
    solo writing-ai-taste <text> / writing-write-natural <text>  中文写作检查/改写
    solo memory-note <text> / memory-search <q>    温域记忆 记/查
    solo optmem-note <text> / optmem-search <q>   OptMem 全局记忆 记/查
    solo onto-to-nt / onto-answer / onto-search <csv>  本体 导出/聚合问答/检索
    solo to-factory-lexicon <csv> / to-review-items <csv>  词典→工厂契约/审查队列
    solo version                 显示版本

拆分说明：原 _dispatch(圈复杂度41) 改为「命令名→处理函数」注册表 + 每个命令一个
处理函数；argparse 注册抽到 _build_parser()（命令名字符串仍在 cli.py，供注册回归断言）。
业务逻辑仍下沉 solo/app.py 与 solo/factory。
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


def _build_parser() -> argparse.ArgumentParser:
    """构造 argparse（子命令注册）。抽离自 main()，命令名注册集中在此。

    按职责分组成 4 个 _add_*_parsers 帮助函数，缩短单函数长度；
    命令名字符串仍在 cli.py，供注册回归断言（test_completeness）。
    """
    parser = argparse.ArgumentParser(prog="solo", description="OPC 与工厂级 FDE 的方法论 Agent")
    sub = parser.add_subparsers(dest="cmd")
    _add_core_parsers(sub)
    _add_factory_parsers(sub)
    _add_survey_parsers(sub)
    _add_delivery_parsers(sub)
    _add_task_backup_parsers(sub)
    _add_code_writing_parsers(sub)
    _add_memory_ontology_parsers(sub)
    return parser


def _add_core_parsers(sub):
    """个人套件核心命令：version/init/setup/config/run/skill-add/obsidian。"""
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


def _add_factory_parsers(sub):
    """工厂套件命令：factory-clean/stats/onto。"""
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


def _add_survey_parsers(sub):
    """需求→验收生命周期（survey 打通入口）。"""
    p_so = sub.add_parser("survey-outline", help="需求访谈提纲(行业数据驱动)")
    p_so.add_argument("--industry", help="行业名(联动实体/量词)")
    p_ss = sub.add_parser("survey-structure", help="结构化一条需求(编号R-xxx)")
    p_ss.add_argument("name", help="调研名")
    p_ss.add_argument("story", help="用户故事/痛点")
    p_ss.add_argument("--category", choices=["生产", "销售", "运维", "管理"], default="生产", help="需求分类")
    p_ss.add_argument("--priority", choices=["P0", "P1", "P2"], default="P2", help="优先级")
    p_ss.add_argument("--acceptance", action="append", help="可验收条款(可多次)")
    p_sr = sub.add_parser("survey-srs", help="生成SRS需求文档")
    p_sr.add_argument("name", help="调研名")
    p_sr.add_argument("--title", help="文档标题(缺省用调研名)")
    p_sa = sub.add_parser("survey-acceptance", help="生成验收清单+勾稽检查")
    p_sa.add_argument("name", help="调研名")


def _add_delivery_parsers(sub):
    """交付辅助(FDE D0/D1/D4)：问题集/词典初稿/报告起草 + 行业联动。"""
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


def _add_task_backup_parsers(sub):
    """任务状态控制面 + 备份恢复（P2-3）。"""
    p_tn = sub.add_parser("task-new", help="新建任务")
    p_tn.add_argument("goal", help="任务目标")
    p_ts = sub.add_parser("task-status", help="查看任务状态")
    p_ts.add_argument("tid", nargs="?", help="任务id(缺省列出所有)")
    p_tg = sub.add_parser("task-gate", help="记录决策门")
    p_tg.add_argument("tid")
    p_tg.add_argument("question", help="待确认问题")
    p_tr = sub.add_parser("task-resolve", help="解决所有待确认门")
    p_tr.add_argument("tid")

    p_bk = sub.add_parser("backup", help="备份记忆/技能/任务")
    p_bk.add_argument("dest", nargs="?", help="备份目录(默认 ~/.solo/backups)")
    p_rs = sub.add_parser("restore", help="恢复备份")
    p_rs.add_argument("src", help="备份目录")


def _add_code_writing_parsers(sub):
    """代码审查 + 写作检查/改写。"""
    p_cr = sub.add_parser("code-review", help="代码审查(静态分析+0-100评分)")
    p_cr.add_argument("file", help="待审 Python 文件")
    p_cr.add_argument("--max-complexity", type=int, default=10, help="圈复杂度阈值")
    p_cr.add_argument("--strict-undefined", action="store_true", help="启用未定义名启发式检查")

    p_wat = sub.add_parser("writing-ai-taste", help="中文文本 AI 味自检(评分+建议+自洽结论)")
    p_wat.add_argument("text")
    p_wat.add_argument("--style", choices=["tweet", "report", "wechat", "paper"], default="report")
    p_wn = sub.add_parser("writing-write-natural", help="风格改写+AI味复检闭环")
    p_wn.add_argument("text")
    p_wn.add_argument("--style", choices=["tweet", "report", "wechat", "paper"], default="tweet")


def _add_memory_ontology_parsers(sub):
    """记忆 note/search（温域 + OptMem）+ 本体导出/问答/检索 + 词典下游。"""
    p_mn = sub.add_parser("memory-note", help="记一条事实(温域记忆)")
    p_mn.add_argument("text")
    p_mn.add_argument("--tag", action="append", help="标签(可多次)")
    p_ms = sub.add_parser("memory-search", help="语义检索记忆")
    p_ms.add_argument("query")
    p_ms.add_argument("--top-k", type=int, default=5)

    p_on = sub.add_parser("optmem-note", help="沉淀经验/方法论进 OptMem 全局记忆")
    p_on.add_argument("text")
    p_os = sub.add_parser("optmem-search", help="语义检索 OptMem 记忆")
    p_os.add_argument("query")
    p_os.add_argument("--top-k", type=int, default=5)

    # 本体：导出 NT / 聚合问答 / 三元组检索（消除 Python-only 无入口断层）
    p_ont = sub.add_parser("onto-to-nt", help="CSV建本体并导出 N-Triples")
    p_ont.add_argument("csv")
    p_ont.add_argument("--entity", help="实体名")
    p_ont.add_argument("--id", dest="id_col", help="主键列")
    p_ont.add_argument("--relations", help="关系声明 JSON 文件")
    p_ont.add_argument("--industry", help="行业名(联动列名中文映射, 供聚合问答)")
    p_oa = sub.add_parser("onto-answer", help="本体聚合问答(计数/极值/枚举/列表)")
    p_oa.add_argument("csv")
    p_oa.add_argument("question", help="问题(如'有多少台设备'/'功率最大的设备'/'设备类型有哪些')")
    p_oa.add_argument("--entity", help="实体名")
    p_oa.add_argument("--id", dest="id_col", help="主键列")
    p_oa.add_argument("--industry", help="行业名(联动列名中文映射, 供聚合问答)")
    p_osr = sub.add_parser("onto-search", help="本体三元组检索")
    p_osr.add_argument("csv")
    p_osr.add_argument("term")
    p_osr.add_argument("--entity", help="实体名")
    p_osr.add_argument("--id", dest="id_col", help="主键列")
    p_osr.add_argument("--industry", help="行业名(联动列名中文映射)")
    p_osr.add_argument("--top-k", type=int, default=5)

    # 词典 → 工厂契约 / review 待确认队列（FDE D1 下游，独立 CLI 入口）
    p_tfl = sub.add_parser("to-factory-lexicon", help="词典初稿→工厂本体 lexicon 契约")
    p_tfl.add_argument("csv")
    p_tfl.add_argument("--industry", help="行业名(联动列名中文映射/实体)")
    p_tfl.add_argument("--table-name", default="数据", help="lexicon 表名")
    p_tfl.add_argument("--entity-cn", default=None, help="实体中文名(缺省用行业默认)")
    p_tri = sub.add_parser("to-review-items", help="词典初稿→闭源 review 待确认队列")
    p_tri.add_argument("csv")
    p_tri.add_argument("--industry", help="行业名(联动列名中文映射)")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = _build_parser()
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


# ─── 命令→处理函数注册表（取代巨型 if/elif，_dispatch 只做查表分发）───
_HANDLERS = {
    "version": lambda a: {"version": __version__},
    "init": lambda a: _h_init(),
    "setup": lambda a: app_mod.check_environment(),
    "config": lambda a: app_mod.config_view(),
    "import-obsidian": lambda a: _h_import_obsidian(a),
    "export-markdown": lambda a: _h_export_markdown(a),
    "skill-add": lambda a: _h_skill_add(a),
    "run": lambda a: _h_run(a),
    "factory-clean": lambda a: _h_factory_clean(a),
    "factory-stats": lambda a: _h_factory_stats(a),
    "factory-onto": lambda a: _h_factory_onto(a),
    "survey-outline": lambda a: _h_survey_outline(a),
    "survey-structure": lambda a: _h_survey_structure(a),
    "survey-srs": lambda a: _h_survey_srs(a),
    "survey-acceptance": lambda a: _h_survey_acceptance(a),
    "draft-questions": lambda a: _assist_draft_questions(a),
    "lexicon-draft": lambda a: _assist_lexicon_draft(a),
    "report-draft": lambda a: _assist_report_draft(a),
    "industry-list": lambda a: _industry_list(),
    "industry-set": lambda a: _industry_set(a),
    "industry-current": lambda a: _industry_current(),
    "task-new": lambda a: _h_task_new(a),
    "task-status": lambda a: _h_task_status(a),
    "task-gate": lambda a: _h_task_gate(a),
    "task-resolve": lambda a: _h_task_resolve(a),
    "backup": lambda a: _backup(a.dest),
    "restore": lambda a: _restore(a.src),
    "code-review": lambda a: _h_code_review(a),
    "writing-ai-taste": lambda a: _h_writing_ai_taste(a),
    "writing-write-natural": lambda a: _h_writing_write_natural(a),
    "memory-note": lambda a: _h_memory_note(a),
    "memory-search": lambda a: _h_memory_search(a),
    "optmem-note": lambda a: _h_optmem_note(a),
    "optmem-search": lambda a: _h_optmem_search(a),
    "onto-to-nt": lambda a: _onto_to_nt(a),
    "onto-answer": lambda a: _onto_answer(a),
    "onto-search": lambda a: _onto_search(a),
    "to-factory-lexicon": lambda a: _assist_to_factory_lexicon(a),
    "to-review-items": lambda a: _assist_to_review_items(a),
}


def _dispatch(args):
    handler = _HANDLERS.get(args.cmd)
    if handler is None:
        return {"error": "unknown command"}
    return handler(args)


# ─── 简单命令处理函数（每个命令一个）───
def _h_init():
    m = memory_mod.Memory()
    m.set_profile("created", _now())
    return {"init": True, "mem_dir": m.dir}


def _h_import_obsidian(args):
    m = memory_mod.Memory()
    return {"imported": m.import_markdown(args.dir)}


def _h_export_markdown(args):
    m = memory_mod.Memory()
    m.export_markdown(args.dir)
    return {"exported_to": args.dir}


def _h_skill_add(args):
    m = memory_mod.Memory()
    return {"added": m.add_fact(args.exp, tags=["skill"])}


def _h_run(args):
    from solo import agent as agent_mod
    return agent_mod.run(args.task, tier=args.tier)


def _h_factory_clean(args):
    return app_mod.data_clean(_load_rows_csv(args.csv), method=args.method, outlier=args.outlier)


def _h_factory_stats(args):
    return app_mod.data_stats(_load_rows_csv(args.csv), col=args.col)


def _h_factory_onto(args):
    return app_mod.build_ontology(_load_rows_csv(args.csv), entity=args.entity,
                                  id_col=args.id_col, relations=args.relations)


def _h_survey_outline(args):
    return app_mod.survey_outline(getattr(args, "industry", None))


def _h_survey_structure(args):
    return app_mod.survey_structure(args.name, args.story, category=args.category,
                                    priority=args.priority, acceptance=args.acceptance)


def _h_survey_srs(args):
    return app_mod.survey_srs(args.name, title=args.title)


def _h_survey_acceptance(args):
    return app_mod.survey_acceptance(args.name)


def _h_task_new(args):
    from solo.task import Task
    t = Task()
    task = t.new(args.goal)
    return {"id": task["id"], "goal": task["goal"], "state": task["state"]}


def _h_task_status(args):
    from solo.task import Task
    t = Task()
    if args.tid:
        return t.status(args.tid)
    return {"tasks": t.list()}


def _h_task_gate(args):
    from solo.task import Task
    t = Task()
    return t.gate(args.tid, args.question)


def _h_task_resolve(args):
    from solo.task import Task
    t = Task()
    return t.resolve(args.tid)


def _h_code_review(args):
    from solo import code_review as cr
    return cr.review_file(args.file, max_complexity=args.max_complexity,
                          strict_undefined=args.strict_undefined)


def _h_writing_ai_taste(args):
    from solo import writing as w
    return w.ai_taste(args.text, style=args.style)


def _h_writing_write_natural(args):
    from solo import writing as w
    return w.write_natural(args.text, style=args.style)


def _h_memory_note(args):
    m = memory_mod.Memory()
    return {"added": m.add_fact(args.text, tags=args.tag), "text": args.text}


def _h_memory_search(args):
    m = memory_mod.Memory()
    return {"hits": m.search(args.query, top_k=args.top_k)}


def _h_optmem_note(args):
    from solo.memory import optmem_note
    ok, msg = optmem_note(args.text)
    return {"ok": ok, "message": msg}


def _h_optmem_search(args):
    from solo.memory import optmem_search
    return {"hits": optmem_search(args.query, top_k=args.top_k)}


# ─── 备份/恢复 ───
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


# ─── 交付辅助（FDE D0/D1/D4）───
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
                           "verdict": ai.get("verdict"),
                           "suggestions": ai["suggestions"][:6],
                           "hard_fails": ai["hard_fails"]}
    return out


def _assist_to_factory_lexicon(args):
    """词典初稿 → 工厂本体 lexicon 契约（FDE D1 下游，独立 CLI 入口）。"""
    from solo.factory.assist import lexicon_draft, to_factory_lexicon
    rows = _load_rows_csv(args.csv)
    headers = list(rows[0].keys()) if rows else []
    d = lexicon_draft(headers, rows[:30], industry=getattr(args, "industry", None))
    return to_factory_lexicon(d, table_name=args.table_name, entity_cn=args.entity_cn,
                              industry=getattr(args, "industry", None))


def _assist_to_review_items(args):
    """词典初稿 → 闭源 review 待确认队列（P2 接线入口）。"""
    from solo.factory.assist import lexicon_draft, to_review_items
    rows = _load_rows_csv(args.csv)
    headers = list(rows[0].keys()) if rows else []
    d = lexicon_draft(headers, rows[:30], industry=getattr(args, "industry", None))
    items = to_review_items(d)
    return {"items": items, "count": len(items)}


# ─── 行业联动 ───
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


# ─── 本体命令 ───
def _onto_build(args):
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
    rows = _load_rows_csv(args.csv)
    if not rows:
        return None, {"error": "数据源无效或为空"}
    o = Ontology(col_cn=col_cn)
    o.from_rows(rows, entity_name=entity, id_col=args.id_col)
    o.build()
    return o, None


def _onto_to_nt(args):
    """CSV → 本体 → N-Triples（消除 Python-only 无入口断层）。"""
    o, err = _onto_build(args)
    if err:
        return err
    return {"nt": o.to_nt(), "entities": list(o.entities.keys()),
            "triples": len(o.triples)}


def _onto_answer(args):
    """本体聚合问答（计数/极值/枚举/列表，闭环 draft_questions 生成题）。"""
    o, err = _onto_build(args)
    if err:
        return err
    return {"question": args.question, "answers": o.answer(args.question, entity=args.entity)}


def _onto_search(args):
    """本体三元组检索。"""
    o, err = _onto_build(args)
    if err:
        return err
    return {"term": args.term, "hits": o.search(args.term, top_k=args.top_k)}


if __name__ == "__main__":
    sys.exit(main())
