# -*- coding: utf-8 -*-
"""code.py — 代码影响分析（改代码前查波及面）。

方法论（AHE/CodeGraph）：改代码前 impact() 查反向依赖，防"改了才炸"。
复刻自 codegraph（方法论借鉴，标准库实现）。
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile

from . import code_review  # 代码审查原子能力（对齐 codeagent-minimal）
from solo import provider as provider_mod

# 排除目录
SKIP_DIRS = {"__pycache__", ".venv", "node_modules", ".git", "dist", "build"}

RE_DEF = re.compile(r"^(?:\s{0,16})(?:async\s+)?(?:def|class)\s+(\w+)", re.M)
RE_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\s+([\w, ]*)|import\s+([\w.]+))", re.M)

# ── Karpathy / Ponytail 原则注入 ──────────────────────
PONYTAIL_SYSTEM = """你是懒人高级开发者。写代码前爬这个阶梯：
1. YAGNI → 不建
2. 代码库已有 → 复用
3. 标准库有 → 用
4. 平台原生有 → 用
5. 已装依赖有 → 用
6. 一行能搞定 → 一行
7. 不行才写最少代码

硬规则：不加未要求的抽象/依赖/样板。删除>添加。最短diff胜出。
不可偷懒：验证/安全/数据保护。非平凡代码留assert或测试。"""


def generate_code(prompt: str, language: str = "python", tier: str = "auto") -> str:
    """生成代码。language 提示语言；tier auto 复杂走远端。"""
    p = provider_mod.Provider.from_file()
    sys_prompt = (
        f"你是资深工程师。用{language}写代码，遵守：\n"
        "1. 极简原则，不加过度抽象\n"
        "2. 只写必要的，可运行的\n"
        "3. 注释简短，说明意图\n"
        f"任务: {prompt}"
    )
    return p.complete(sys_prompt, tier=tier)


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

    def overview(self) -> dict:
        """代码库概览（FDE 接手项目时快速理解）。"""
        # 核心模块：被最多文件依赖的
        ranked = sorted(self.rev.items(), key=lambda kv: len(kv[1]), reverse=True)
        core = [{"file": os.path.basename(f), "depended_by": len(deps)}
                for f, deps in ranked[:5]]
        # 统计
        by_dir = {}
        for f in self.files:
            d = os.path.dirname(os.path.relpath(f, self.root)) or "."
            by_dir[d] = by_dir.get(d, 0) + 1
        return {
            "files": len(self.files),
            "symbols": len(self.symbols),
            "top_core_modules": core,
            "files_by_dir": dict(sorted(by_dir.items(), key=lambda kv: -kv[1])),
        }

    def explain(self, symbol: str) -> dict:
        """理解一个符号：定义 + 谁用它 + 它依赖谁。对标 CodeAgent 符号理解。"""
        meta = self.symbols.get(symbol)
        if not meta:
            return {"error": f"symbol not found: {symbol}"}
        f = meta["file"]
        return {
            "symbol": symbol,
            "kind": meta["kind"],
            "defined_in": os.path.relpath(f, self.root),
            "line": meta["line"],
            "used_by": [os.path.relpath(x, self.root) for x in self.rev.get(f, [])],
            "depends_on": [os.path.relpath(x, self.root) for x in self.deps.get(f, [])],
        }

    def review(self, file: str) -> dict:
        """代码审查（对齐 codeagent-minimal 口径）。

        在原有轻量检查（裸 except、TODO/FIXME）之上，合并 codeagent 的全量静态分析
        （语法/复杂度/安全/网络/BUG/架构/复用）与 0-100 评分，保证与 codeagent 得分一致。
        """
        path = self._find(file)
        if not path or not os.path.exists(path):
            return {"error": f"file not found: {file}"}
        try:
            src = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            return {"error": f"cannot read: {file}"}
        issues = []
        lines = src.splitlines()
        # 裸 except
        for i, ln in enumerate(lines):
            s = ln.strip()
            if s == "except:" or s.startswith("except :"):
                issues.append({"line": i+1, "severity": "warn", "type": "bare-except", "msg": "裸 except 会吞掉所有异常"})
        # TODO/FIXME
        for i, ln in enumerate(lines):
            if "TODO" in ln or "FIXME" in ln:
                issues.append({"line": i+1, "severity": "info", "type": "todo", "msg": ln.strip()[:60]})
        # 合并 codeagent 对齐的静态分析 + 0-100 评分
        static = code_review.review_file(path)
        return {"file": os.path.relpath(path, self.root),
                "issues": issues, "total": len(issues),
                "static_score": static["static_score"],
                "static_issues": static["static_issues"]}

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
        base = os.path.basename(file)
        for f in self.files:
            if base and os.path.basename(f) == base:
                return f
            if file in f:
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


# ═══════════════════════════════════════════════
# 测试生成（纯 AST）
# ═══════════════════════════════════════════════

def _extract_type_hint(annotation):
    if annotation is None:
        return ""
    try:
        if isinstance(annotation, ast.Name):
            return annotation.id
        if isinstance(annotation, ast.Constant):
            return str(annotation.value)
        if isinstance(annotation, ast.Index):
            return _extract_type_hint(annotation.value)
        if isinstance(annotation, (ast.Subscript, ast.Tuple, ast.List)):
            return "list"
    except Exception:
        return ""
    return ""


def _is_bool_function(name, node) -> bool:
    return name.startswith("is_") or name.startswith("has_") or name.startswith("can_") or \
        name.startswith("check") or "is_valid" in name


def _boundary_values(hints: dict) -> list:
    """根据类型注解推断边界值。int/float→零+负数；str→空串。"""
    bv = {"int": ["0", "-1"], "float": ["0", "-1.5"], "str": ["''", "'a'"],
          "list": ["[]", "[1]"]}
    return bv.get(hints.get(""), [])


def _gen_python_tests(path, content) -> str:
    """AST 生成参数化测试：基础 + 边界值。"""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    mod = path.replace("/", ".").replace(".py", "").lstrip(".")
    funcs, methods = [], []
    for n in ast.iter_child_nodes(tree):
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
            params = [a.arg for a in n.args.args]
            has_return = any(isinstance(x, ast.Return) for x in ast.walk(n))
            hints = {a.arg: _extract_type_hint(a.annotation) for a in n.args.args if a.annotation}
            funcs.append((n.name, params, has_return, hints, n))
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, ast.FunctionDef) and not m.name.startswith("_"):
                    params = [x.arg for x in m.args.args if x.arg not in ("self", "cls")]
                    has_return = any(isinstance(x, ast.Return) for x in ast.walk(m))
                    hints = {a.arg: _extract_type_hint(a.annotation) for a in m.args.args if a.annotation}
                    methods.append((n.name, m.name, params, has_return, hints, m))

    lines = [f'"""tests for {path}"""',
             "import sys; sys.path.insert(0, '.')",
             f"import {mod}", "import pytest", ""]

    for fn, args, hr, hints, node in funcs:
        arglist = ", ".join(["1"] * max(len(args), 1))
        lines += [f"def test_{fn}_basic():", f"    result = {mod}.{fn}({arglist})"]
        if hr:
            lines.append("    assert result is not None")
        lines.append("")
        # 边界值
        for bv in _boundary_values(hints):
            lines += [f"def test_{fn}_boundary_{bv.replace(chr(39),'').replace(chr(45),'neg')}():",
                      f"    result = {mod}.{fn}({bv})", "    assert result is not None", ""]

    for cls, fn, args, hr, hints, node in methods:
        arglist = ", ".join(["1"] * max(len(args), 1))
        lines += [f"def test_{cls}_{fn}_basic():",
                  f"    obj = {mod}.{cls}()", f"    result = obj.{fn}({arglist})"]
        if hr:
            lines.append("    assert result is not None")
        lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════
# CodeAgent（生成/审查/测试全链路）
# ═══════════════════════════════════════════════
class CodeAgent:
    """代码生成/审查/测试全链路（接 solo provider，零依赖）。"""

    def __init__(self, provider=None):
        self.provider = provider or provider_mod.Provider.from_file()
        self._reuse_index = {}   # path -> {symbols/deps}(懒加载)

    # ---- 模型调用（适配 provider）----
    def _gen(self, prompt, tier="remote"):
        """生成文本。生成走远端，审查走本地。"""
        return self.provider.complete(prompt, tier=tier)

    # ---- 静态分析（只读，零模型，单一事实来源 = code_review）----
    def analyze(self, code: str) -> dict:
        """静态分析一段代码，返回 code_review._static_analyze 全量结果。"""
        return code_review._static_analyze(code)

    # ---- think：方案设计 ----
    def think(self, task: str, language="python") -> dict:
        """分析需求，输出方案设计（JSON）。"""
        prompt = (PONYTAIL_SYSTEM + "\n\n分析需求输出 JSON 方案：\n"
                  '{"plan":"一句话","assumptions":[],"files_needed":[],"simplest_approach":""}\n'
                  f"需求：{task}  语言：{language}  极简优先。")
        try:
            out = self._gen(prompt, tier="remote")
            return self._parse_json(out)
        except Exception:
            return {"plan": "直接实现", "files_needed": ["main.py"],
                    "simplest_approach": task}

    # ---- implement：代码生成 ----
    def implement(self, task: str, language="python", loop=False, max_iter=3) -> dict:
        """生成代码。支持 loop 迭代优化（生成→静态审查→改进）。"""
        prompt = (PONYTAIL_SYSTEM + "\n\n"
                  f"用{language}写代码。只输出代码，不要解释。\n任务：{task}")
        code = self._gen(prompt, tier="remote")
        if not code:
            return {"error": "生成失败（模型无返回）"}
        code = self._strip_code_fences(code)

        versions = []
        best = code
        if loop:
            for i in range(max_iter):
                versions.append({"iter": i + 1, "score": self._score_code(best)})
                issues = self._static_issues(best)
                if not issues:
                    break
                # 用问题列表引导改进
                fix_prompt = (PONYTAIL_SYSTEM + "\n\n改进代码，修复以下问题：\n" +
                              "\n".join(f"- {i['title']}" for i in issues[:5]) +
                              f"\n原代码：\n{best}\n输出改进后完整代码。")
                try:
                    new = self._gen(fix_prompt, tier="remote")
                    if new and len(new) > 10:
                        best = new
                except Exception:
                    pass
        return {"files": {"main.py": best}, "score": self._score_code(best),
                "summary": f"生成 {language} 代码", "issues": self._static_issues(best),
                "versions": versions}

    # ---- review：双层审查（取代 gen.review_code 的重叠）----
    def review(self, code: dict) -> dict:
        """双层审查：静态分析(硬) + 模型审查(软)。code: {文件名: 源码}。"""
        all_issues = []
        for fname, content in (code or {}).items():
            static = code_review._static_analyze(content)
            for i in static["all_issues"]:
                i["file"] = fname
            all_issues += static["all_issues"]
        # 模型审查（本地）
        model_issues = []
        try:
            sample = next(iter((code or {}).values()), "")
            if sample:
                out = self._gen(
                    "你是代码审查者。审查代码，指出真实bug/过度工程/可改进处，"
                    "只报真实问题。\n\n" + sample[:3000], tier="local")
                if out and "无问题" not in out and out.strip():
                    model_issues.append({"severity": "info", "title": "模型审查",
                                         "suggestion": out.strip()[:300]})
        except Exception:
            pass
        # 评分对齐 codeagent：score = max(0, 100 - Σ severity权重)
        penalty = sum(code_review.SEVERITY_WEIGHTS.get(i["severity"], 5) for i in all_issues)
        score = max(0, 100 - penalty)
        return {"score": score, "issues": all_issues, "model_issues": model_issues,
                "summary": f"静态{len(all_issues)}条 + 模型审查，评分{score}（对齐codeagent口径）"}

    # ---- test/run_tests ----
    def test(self, code: dict) -> dict:
        """为代码生成测试文件。"""
        tests = {}
        for fname, content in (code or {}).items():
            if fname.endswith(".py"):
                t = _gen_python_tests(fname, content)
                if t:
                    tests[fname.replace(".py", "_test.py")] = t
        return {"test_files": tests}

    def run_tests(self, test_files: dict, workdir=".") -> dict:
        """运行生成的测试。临时目录写入，pytest 执行。"""
        if not test_files:
            return {"ok": False, "error": "无测试文件"}
        tmpdir = tempfile.mkdtemp(prefix="solo_agent_")
        try:
            for name, content in test_files.items():
                path = os.path.join(tmpdir, os.path.basename(name))
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            r = subprocess.run([sys.executable, "-m", "pytest", tmpdir, "-q"],
                               capture_output=True, text=True, timeout=120)
            return {"ok": r.returncode == 0, "exit_code": r.returncode,
                    "output": (r.stdout or "")[-1500:]}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ---- 内部 ----
    def _static_issues(self, code: str) -> list:
        return code_review._static_analyze(code)["all_issues"]

    def _score_code(self, code: str) -> int:
        # 评分对齐 codeagent：直接取 code_review._static_analyze 的 score
        return code_review._static_analyze(code)["score"]

    def _parse_json(self, text: str) -> dict:
        """从模型输出提取 JSON（markdown 代码块容错）。"""
        if not text:
            return {}
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}

    def _strip_code_fences(self, text: str) -> str:
        """去掉模型输出里的 markdown 代码块包裹（```python ... ```）。"""
        if not text:
            return text
        m = re.search(r"```[a-zA-Z]*\n(.*?)```", text, re.S)
        if m:
            return m.group(1).strip()
        return text.strip()
