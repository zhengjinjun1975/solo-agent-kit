# -*- coding: utf-8 -*-
"""cli.py — FDE 原子化统一入口。

命令：scan / registry / status / run / chain / evolve / capabilities / selftest
对齐方案 §3.4。纯标准库。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fde_runtime.loader import AgentRuntime  # noqa: E402


def _out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _make_runtime():
    return AgentRuntime(atoms_root=os.path.join(_ROOT, "atoms"),
                        registry_path=os.path.join(_ROOT, "registry.json"))


def cmd_scan(rt, args):
    ms = rt.scan(tolerate=not args.strict)
    _out({"count": len(ms), "atoms": ms})


def cmd_registry(rt, args):
    rt.scan(tolerate=True)
    rt.resolve()
    if args.write:
        reg = rt.write_registry()
        _out({"written": True, "schema": reg["schema"], "count": len(reg["agents"])})
    else:
        reg = rt.load_registry()
        _out({"count": len(reg.get("agents", [])) if reg else 0, "registry": reg})


def cmd_status(rt, args):
    rt.scan(tolerate=True)
    rt.load()
    _out(rt.status())


def cmd_capabilities(rt, args):
    rt.scan(tolerate=True)
    rt.load()
    _out({"capabilities": rt.capabilities()})


def cmd_run(rt, args):
    rt.scan(tolerate=True)
    rt.load()
    params = {}
    if args.params:
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as e:
            print(f"参数解析失败: {e}", file=sys.stderr)
            sys.exit(1)
    env = rt.run_capability(args.capability, **params)
    _out(env)


def cmd_chain(rt, args):
    rt.scan(tolerate=True)
    rt.load()
    asm_path = args.assembly or os.path.join(_ROOT, "assemblies", "fde-workflow.json")
    with open(asm_path, encoding="utf-8") as f:
        asm = json.load(f)
    flow = rt.run_flow(asm, workdir=args.dir)
    _out(flow)


def cmd_evolve(rt, args):
    from fde_runtime import evolve as _ev
    r = _ev.evolve(args.observation, target=args.target,
                   feedback=args.feedback, **json.loads(args.params or "{}"))
    _out(r)


def cmd_selftest(rt, args):
    """逐原子独立自测（A3 铁律）。"""
    rt.scan(tolerate=True)
    results = {}
    for m in rt.manifests:
        entry = os.path.join(_ROOT, m["path"], m["entry"])
        ec = os.system(f'"{sys.executable}" "{entry}" > /dev/null 2>&1')
        results[m["name"]] = "PASS" if ec == 0 else "FAIL"
    fails = [k for k, v in results.items() if v == "FAIL"]
    _out({"results": results, "total": len(results), "failed": fails})


def main(argv=None):
    p = argparse.ArgumentParser(prog="fde-runtime", description="FDE 原子化统一入口")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan", help="扫描原子").add_argument("--strict", action="store_true")
    sub.add_parser("status", help="运行时状态（生命周期）")
    sub.add_parser("capabilities", help="能力清单")
    pr = sub.add_parser("registry", help="注册表")
    pr.add_argument("--write", action="store_true", help="扫描并写回 registry.json")

    run = sub.add_parser("run", help="运行单个能力")
    run.add_argument("capability")
    run.add_argument("--params", default=None, help="JSON 字符串参数")

    chain = sub.add_parser("chain", help="运行组装链 run_flow")
    chain.add_argument("--assembly", default=None, help="装配 JSON 路径")
    chain.add_argument("--dir", default=None, help="共享工作目录")

    ev = sub.add_parser("evolve", help="自进化反馈闭环")
    ev.add_argument("observation")
    ev.add_argument("--target", default=None)
    ev.add_argument("--feedback", type=float, default=None)
    ev.add_argument("--params", default=None)

    sub.add_parser("selftest", help="11 原子独立自测")

    args = p.parse_args(argv)
    rt = _make_runtime()
    if args.cmd == "scan":
        cmd_scan(rt, args)
    elif args.cmd == "status":
        cmd_status(rt, args)
    elif args.cmd == "capabilities":
        cmd_capabilities(rt, args)
    elif args.cmd == "registry":
        cmd_registry(rt, args)
    elif args.cmd == "run":
        cmd_run(rt, args)
    elif args.cmd == "chain":
        cmd_chain(rt, args)
    elif args.cmd == "evolve":
        cmd_evolve(rt, args)
    elif args.cmd == "selftest":
        cmd_selftest(rt, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
