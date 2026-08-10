# -*- coding: utf-8 -*-
"""cli.py — solo 命令入口（agent-first，JSON out + 分级退出码）。

命令：
    solo init                   初始化记忆库
    solo run "<任务>"            走方法论（记忆装载→推理→行动→记忆提交）
    solo skill-add "<经验>"      从任务提取可复用经验
    solo import-obsidian <dir>   导入 Obsidian 笔记为记忆
    solo export-markdown <dir>   导出记忆为 Markdown
    solo version                 显示版本
"""
from __future__ import annotations

import argparse
import json
import sys

from solo import __version__
from solo import memory as memory_mod
from solo import provider as provider_mod


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="solo", description="一人公司方法论 Agent")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("version", help="显示版本")
    sub.add_parser("init", help="初始化记忆库")
    p_run = sub.add_parser("run", help="运行一个任务（走完整方法论）")
    p_run.add_argument("task", help="任务描述")
    p_run.add_argument("-", "--stdin", action="store_true", help="从 stdin 读任务正文")
    p_skill = sub.add_parser("skill-add", help="从任务提取可复用经验")
    p_skill.add_argument("exp", help="经验内容")
    p_imp = sub.add_parser("import-obsidian", help="导入 Obsidian 笔记")
    p_imp.add_argument("dir")
    p_exp = sub.add_parser("export-markdown", help="导出记忆为 Markdown")
    p_exp.add_argument("dir")

    args = parser.parse_args(argv)

    # JSON 输出 + 分级退出码
    try:
        result = _dispatch(args)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False))
        return provider_mod.EXIT_OK
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
    if cmd == "import-obsidian":
        m = memory_mod.Memory()
        n = m.import_markdown(args.dir)
        return {"imported": n}
    if cmd == "export-markdown":
        m = memory_mod.Memory()
        m.export_markdown(args.dir)
        return {"exported_to": args.dir}
    if cmd == "skill-add":
        m = memory_mod.Memory()
        added = m.add_fact(args.exp, tags=["skill"])
        return {"added": added}
    if cmd == "run":
        return _run(args.task)
    return {"error": "unknown command"}


def _run(task: str):
    """最小闭环：记忆装载 → provider 推理 → 记忆提交。"""
    m = memory_mod.Memory()
    # 1. 记忆装载（热域画像 + 温域相关事实）
    profile = m.profile_text()
    related = m.search(task, top_k=3)
    related_txt = "\n".join(f"- {f['text']}" for f in related)

    # 2. 推理（默认本地，轻量优先）
    prompt = f"任务: {task}\n\n我已知的用户画像:\n{profile}\n\n相关记忆:\n{related_txt}\n\n请给出处理建议(简洁,中文):"
    p = provider_mod.Provider.from_config({})
    text = p.complete(prompt, tier="local")

    # 3. 记忆提交：任务有价值 → 记入事实层
    m.add_fact(task, tags=["task"])

    return {"task": task, "suggestion": text, "memory_dir": m.dir}


def _now():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    sys.exit(main())
