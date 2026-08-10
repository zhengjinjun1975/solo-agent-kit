# -*- coding: utf-8 -*-
"""example_03_oss_preflight.py — 一人公司场景③：开源发布前检查。

展示开源合规方法论：脱敏扫描 + 代码影响分析 + 版本核查。
跑法：python examples/example_03_oss_preflight.py <项目目录> [项目名]

体现"方法论完整"：开源不是 git push 了事，是脱敏/影响/版本三关。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo import code as code_mod

# 脱敏扫描模式（敏感物）
SENSITIVE = [
    ("API key", r"api_key\s*=\s*['\"][^'\"]+"),
    ("密钥", r"sk-[A-Za-z0-9]+"),
    ("环境变量路径", r"DEEPSEEK_API_KEY|ZHIPU"),
    ("Windows 绝对路径", r"[A-Za-z]:\\\\"),
    ("home 目录", r"AppData|knowledge-base"),
    ("内部工具名", r"OpenClaw|CodeAgent"),
]


def scan_sensitive(path: str) -> list:
    """扫描目录下所有源码/文档的敏感物。跳过本工具自身（避免规则误报）。"""
    self_name = os.path.basename(__file__)
    findings = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".venv", "node_modules")]
        for fn in files:
            if fn == self_name:  # 跳过自身，避免扫描规则被误报
                continue
            if not fn.endswith((".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt")):
                continue
            full = os.path.join(root, fn)
            try:
                with open(full, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        for name, pat in SENSITIVE:
                            if re.search(pat, line):
                                findings.append((os.path.relpath(full, path), i, name, line.strip()[:50]))
            except Exception:
                continue
    return findings


def main(proj_dir: str, name: str = None):
    print(f"== 场景③：开源发布前检查「{proj_dir}」 ==\n")

    # 1. 脱敏扫描
    print("[1/3] 脱敏扫描...")
    findings = scan_sensitive(proj_dir)
    if findings:
        print(f"  ⚠️ 发现 {len(findings)} 处敏感物：")
        for rel, ln, kind, line in findings[:10]:
            print(f"    {rel}:{ln} [{kind}] {line}")
    else:
        print("  ✅ 无敏感物残留")

    # 2. 代码影响分析（改代码前了解波及面）
    print("[2/3] 代码影响分析...")
    proj_name = name or os.path.basename(proj_dir)
    cg = code_mod.CodeGraph()
    n = cg.index(proj_dir)
    print(f"  索引 {n} 个 Python 文件, {len(cg.symbols)} 个符号")
    # 找最核心的文件（被最多人引用的）
    if cg.rev:
        core = max(cg.rev.items(), key=lambda kv: len(kv[1]))
        core_file = os.path.basename(core[0])
        print(f"  核心文件 {core_file} 被 {len(core[1])} 个文件依赖——改它影响面最大")

    # 3. 版本核查
    print("[3/3] 版本核查...")
    version_ok = True
    for root, _, files in os.walk(proj_dir):
        for fn in files:
            if fn in ("__init__.py", "pyproject.toml"):
                full = os.path.join(root, fn)
                with open(full, encoding="utf-8", errors="ignore") as f:
                    txt = f.read()
                m = re.search(r'version\s*=\s*["\']([0-9.]+)["\']', txt)
                if m:
                    print(f"  {os.path.relpath(full, proj_dir)}: v{m.group(1)}")
    print("  (发布前确认各文件版本一致)")

    print("\n== 完成：开源发布前检查 ==")
    return {"sensitive": len(findings), "files": n}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python examples/example_03_oss_preflight.py <项目目录> [项目名]")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
