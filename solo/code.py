# -*- coding: utf-8 -*-
"""code.py — 代码影响分析（改代码前查波及面）。

方法论（AHE/CodeGraph）：改代码前 impact() 查反向依赖，防"改了才炸"。
复刻自 codegraph（方法论借鉴，标准库实现）。
"""
from __future__ import annotations

import json
import os
import re

# 排除目录
SKIP_DIRS = {"__pycache__", ".venv", "node_modules", ".git", "dist", "build"}

RE_DEF = re.compile(r"^(?:async\s+)?(?:def|class)\s+(\w+)", re.M)
RE_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\s+([\w, ]*)|import\s+([\w.]+))", re.M)


class CodeGraph:
    """Python 项目符号/依赖/影响分析图。零依赖，JSON 缓存。"""

    def __init__(self):
        self.root = ""
        self.files = []
        self.symbols = {}   # symbol -> {"file","kind","line"}
        self.deps = {}      # file -> [imported files]
        self.rev = {}       # file -> [files importing it]

    def index(self, root: str) -> int:
        """索引一个 Python 项目。返回文件数。"""
        self.root = os.path.abspath(root)
        files = []
        for dp, dirs, fn in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for n in fn:
                if n.endswith(".py"):
                    files.append(os.path.join(dp, n))
        self.files = sorted(files)

        # 模块名映射
        file_to_mod = {}
        for f in files:
            rel = os.path.relpath(f, self.root).replace("\\", "/")[:-3]
            file_to_mod[f] = rel.replace("/", ".")

        self.symbols, self.deps = {}, {}
        for f in files:
            try:
                src = open(f, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            lines = src.split("\n")
            for m in RE_DEF.finditer(src):
                ln = src[:m.start()].count("\n") + 1
                line = lines[ln - 1]
                kind = "class" if "class " in line else "def"
                name = m.group(1)
                if name not in self.symbols:
                    self.symbols[name] = {"file": f, "kind": kind, "line": ln}
            mods = set()
            for m in RE_IMPORT.finditer(src):
                from_mod, from_names, imp_mod = m.group(1), m.group(2), m.group(3)
                if imp_mod:  # `import x`
                    mods.add(imp_mod)
                elif from_mod:  # `from x import a, b`
                    mods.add(from_mod)
                    for nm in from_names.split(","):
                        nm = nm.strip()
                        if nm:
                            mods.add(from_mod + "." + nm)
            dep_files = set()
            for mo in mods:
                r = self._resolve(mo, file_to_mod)
                if r and r != f:
                    dep_files.add(r)
            self.deps[f] = sorted(dep_files)

        # 反向依赖
        self.rev = {f: [] for f in files}
        for f, deps in self.deps.items():
            for d in deps:
                self.rev.setdefault(d, []).append(f)
        return len(files)

    def impact(self, file: str) -> list:
        """改某文件会波及谁（反向依赖 + 跨文件符号引用）。"""
        f = self._find(file)
        if not f:
            return []
        imp = list(self.rev.get(f, []))
        # 跨文件符号引用
        for sym, meta in self.symbols.items():
            if meta["file"] == f:
                for ref_file, refs in self._refs().items():
                    if sym in refs and ref_file not in imp and ref_file != f:
                        imp.append(ref_file)
        return sorted(set(imp))

    def query(self, symbol: str) -> dict:
        """查符号定义位置。"""
        return self.symbols.get(symbol)

    def deps(self, file: str) -> list:
        f = self._find(file)
        return self.deps.get(f, [])

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"root": self.root, "files": self.files, "symbols": self.symbols,
                       "deps": self.deps, "rev": self.rev}, fh, ensure_ascii=False)

    def load(self, path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        self.root, self.files = d["root"], d["files"]
        self.symbols, self.deps, self.rev = d["symbols"], d["deps"], d["rev"]

    # ---- 内部 ----
    def _resolve(self, module: str, file_to_mod: dict):
        parts = module.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            for f, m in file_to_mod.items():
                if m == cand:
                    return f
        for f, m in file_to_mod.items():
            if os.path.splitext(os.path.basename(f))[0] == parts[-1]:
                return f
        return None

    def _find(self, file: str) -> str:
        for f in self.files:
            if file in os.path.basename(f) or file in f:
                return f
        return None

    def _refs(self) -> dict:
        """symbol -> [files referencing it]（懒计算）。"""
        refs = {}
        for sym, meta in self.symbols.items():
            refs[sym] = []
            for f in self.files:
                if f == meta["file"]:
                    continue
                try:
                    if re.search(r"\b" + re.escape(sym) + r"\b",
                                 open(f, encoding="utf-8", errors="ignore").read()):
                        refs[sym].append(f)
                except Exception:
                    pass
        return refs
