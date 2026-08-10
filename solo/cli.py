# -*- coding: utf-8 -*-
"""cli.py — solo 命令入口（agent-first，JSON out + 分级退出码）。

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
from solo._util import is_num as _num
from solo import memory as memory_mod
from solo import provider as provider_mod
from solo.factory import clean as clean_mod
from solo.factory import stats as stats_mod
from solo.factory import ontology as ontology_mod


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

    # 厂区运维配置与定位
    p_site = sub.add_parser("site", help="厂区配置与定位")
    ssub = p_site.add_subparsers(dest="site_cmd")
    ssub.add_parser("list", help="列出所有厂区")
    ssub.add_parser("devices", help="列出当前厂区设备台账")
    p_suse = ssub.add_parser("use", help="切换到指定厂区")
    p_suse.add_argument("name")
    p_sadd = ssub.add_parser("add-site", help="新增厂区")
    p_sadd.add_argument("name")
    p_sadd.add_argument("--location", default="", help="厂区位置")
    p_sadd.add_argument("--contact", default="", help="联系人")
    p_sdev = ssub.add_parser("add-device", help="添加设备到当前厂区")
    p_sdev.add_argument("name")
    p_sdev.add_argument("host")
    p_sdev.add_argument("--user", default="", help="SSH用户")
    p_sdev.add_argument("--port", type=int, default=22, help="SSH端口")
    p_sdev.add_argument("--group", default="", help="设备分组")
    p_sdev.add_argument("--role", default="", help="设备角色")
    p_srm = ssub.add_parser("rm-device", help="移除设备")
    p_srm.add_argument("name")
    p_srole = ssub.add_parser("role", help="查看/设置部署角色")
    p_srole.add_argument("value", nargs="?", help="laptop / on-site（缺省查看）")

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


def _dispatch(args):
    cmd = args.cmd
    if cmd == "version":
        return {"version": __version__}
    if cmd == "init":
        m = memory_mod.Memory()
        m.set_profile("created", _now())
        return {"init": True, "mem_dir": m.dir}
    if cmd == "setup":
        return _setup()
    if cmd == "config":
        return _config()
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
        return _run(args.task, args.tier)
    if cmd == "factory-clean":
        return _factory_clean(args)
    if cmd == "factory-stats":
        return _factory_stats(args)
    if cmd == "factory-onto":
        return _factory_onto(args)
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
    if cmd == "site":
        return _site(args)
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


def _run(task: str, tier: str = "auto"):
    """循环五态：记忆装载 → skill 注入 → 推理 → 记忆提交。"""
    from solo import agent as agent_mod
    return agent_mod.run(task, tier=tier)


def _setup():
    """部署检查：环境 / 本地模型 / 配置 / 初始化。"""
    import subprocess
    checks = {}
    # 1. Python 版本
    checks["python"] = {"ok": sys.version_info >= (3, 9), "version": f"{sys.version_info.major}.{sys.version_info.minor}"}
    # 2. 本地 Ollama
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            models = [m.get("name", "") for m in json.load(r).get("models", [])]
        checks["ollama"] = {"ok": True, "models": models[:5]}
    except Exception:
        checks["ollama"] = {"ok": False, "error": "本地 Ollama 未运行（记忆语义检索需要）"}
    # 3. 配置
    cfg = provider_mod.load_config()
    checks["config"] = {"ok": bool(cfg), "has_provider_yaml": bool(cfg)}
    # 4. 记忆库
    m = memory_mod.Memory()
    checks["memory"] = {"ok": True, "dir": m.dir, "facts": len(m._load(m._facts_path, []))}
    return {"checks": checks,
            "all_ok": all(c.get("ok", True) for c in checks.values())}


def _config():
    """查看/校验 provider.yaml 配置（脱敏显示）。"""
    cfg = provider_mod.load_config()
    if not cfg:
        return {"configured": False,
                "hint": "未找到 provider.yaml。复制 provider.yaml.example 为 provider.yaml 并填写。"}
    p = cfg.get("provider", {})
    out = {"configured": True}
    for k in ("local", "remote", "embed"):
        item = p.get(k, {})
        clean_item = dict(item)
        if "api_key_env" in clean_item:  # 只显示 env 名，不显示 key
            clean_item["api_key_env"] = clean_item["api_key_env"] + " (从环境变量读)"
        out[k] = clean_item
    return out


def _factory_clean(args):
    """工厂数据清洗。"""
    cl = clean_mod.DataCleaner()
    rows = cl.load_csv(args.csv)
    out = cl.clean(rows, fill_missing=args.method, outlier_method=args.outlier)
    return {"input": len(rows), "output": len(out), "report": cl.report}


def _factory_stats(args):
    """工厂数据分析。"""
    cl = clean_mod.DataCleaner()
    rows = cl.load_csv(args.csv)
    col = args.col
    if not col:  # 自动选第一个数值列
        types = {}
        for c in rows[0].keys():
            if rows[0].get(c, "").strip():
                types[c] = cl.report.get("types", {}).get(c) or "text"
        col = next((c for c, t in types.items() if t in ("integer", "float")), None)
    if not col:
        return {"error": "未找到数值列，用 --col 指定"}
    values = [float(r[col]) for r in rows if r.get(col, "").strip() and _num(r.get(col))]
    return {
        "column": col,
        "describe": stats_mod.describe(values),
        "anomalies": stats_mod.detect_anomaly(values, method="iqr"),
        "control_chart": stats_mod.control_chart(values),
        "trend": stats_mod.trend(values),
    }


def _factory_onto(args):
    """工厂本体建模。"""
    o = ontology_mod.Ontology()
    relations = None
    if args.relations:
        with open(args.relations, encoding="utf-8") as f:
            relations = json.load(f)
        # 兼容多种结构：
        #   {列: {rel,target_class,label}}                          直接对象属性
        #   {实体名: {object_properties: {...}}}                   多实体关系配置
        #   {object_properties: {...}}                             单实体配置
        if isinstance(relations, dict):
            if "object_properties" in relations:
                relations = relations["object_properties"]
            elif relations and all(isinstance(v, dict) and "object_properties" in v
                                   for v in relations.values() if isinstance(v, dict)):
                # 取匹配实体名的那份；若 args.entity 不在 relations 键里则用第一个
                ent = args.entity if (args.entity and args.entity in relations) else next(iter(relations))
                relations = relations[ent].get("object_properties", relations[ent])
    o.from_csv(args.csv, entity_name=args.entity, id_col=args.id_col, relations=relations)
    o.build()
    return {"entities": list(o.entities.keys()), "triples": len(o.triples),
            "summary": o.entity_summary()}



def _site(args):
    """厂区配置与定位命令分发。"""
    from solo.site import Site
    s = Site()
    sc = args.site_cmd
    if sc == "list":
        return {"role": s.role, "current_site": s.current_site,
                "sites": s.list_sites()}
    if sc == "use":
        r = s.use(args.name)
        return r if not r["ok"] else {"ok": True, "current_site": r["current_site"],
                                       "devices": [d["name"] for d in s.devices()]}
    if sc == "add-site":
        return s.add_site(args.name, args.location, args.contact)
    if sc == "devices":
        return {"current_site": s.current_site, "devices": s.devices()}
    if sc == "add-device":
        return s.add_device(args.name, args.host, args.user, args.port,
                            args.group, args.role)
    if sc == "rm-device":
        return s.rm_device(args.name)
    if sc == "role":
        if args.value:
            return s.set_role(args.value)
        return {"role": s.role}
    return {"error": "未知 site 子命令", "cmd": sc}


def _now():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    sys.exit(main())
