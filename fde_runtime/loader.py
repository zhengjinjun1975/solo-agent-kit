# -*- coding: utf-8 -*-
"""loader.py — 原子扫描 / 注册表 / 依赖解析 / load / run / 降级。

对齐生态 loader：
- scan_atoms(atoms_root) 扫描目录树，读 manifest + 校验（tolerate 容错跳过非法项）。
- resolve_order 拓扑排序（被依赖者先加载）+ 环检测 + 开源禁依赖闭源边界。
- AgentRuntime 持所有已加载原子 + capability→atom 索引 + run_capability 统一路由。
"""
from __future__ import annotations

import importlib.util
import json
import os

from fde_runtime import base
from fde_runtime.manifest import ManifestError, load as _manifest_load

DEFAULT_ATOMS_ROOT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "atoms")
DEFAULT_REGISTRY = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "registry.json")


class DependencyCycleError(Exception):
    """依赖环。"""


class LoadError(Exception):
    """加载失败。"""


def _load_atom_class(atom_dir: str, entry: str):
    """按文件路径加载原子 main.py 中的 AtomicAgent 子类。

    规避多原子同名模块 import 冲突：按路径唯一模块名加载。
    """
    path = os.path.join(atom_dir, entry)
    if not os.path.exists(path):
        raise LoadError(f"entry 不存在: {path}")
    name = os.path.basename(atom_dir)
    spec = importlib.util.spec_from_file_location(f"fde_atom_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 找 AtomicAgent 子类（排除基类本身）
    cls = None
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if (isinstance(obj, type) and issubclass(obj, base.AtomicAgent)
                and obj is not base.AtomicAgent):
            cls = obj
            break
    if cls is None:
        raise LoadError(f"{path} 未定义 AtomicAgent 子类")
    return cls


def scan_atoms(atoms_root: str = DEFAULT_ATOMS_ROOT, tolerate: bool = True) -> list:
    """扫描 atoms/ 目录树，返回 [{name, agent, version, open_source, license, path,
    capabilities, depends_on}]，manifest 校验失败容错跳过（print 一行提示）。"""
    out = []
    if not os.path.isdir(atoms_root):
        return out
    for root, _dirs, files in os.walk(atoms_root):
        if "manifest.json" not in files:
            continue
        mpath = os.path.join(root, "manifest.json")
        try:
            m = _manifest_load(mpath)
            entry = m.get("entry")
            # 探能力：加载类拿 capabilities（失败则空，不阻断）
            caps = []
            try:
                cls = _load_atom_class(root, entry)
                caps = cls.capabilities(cls) or []
            except Exception:  # noqa: BLE001
                caps = []
            rel = _try_rel(root, os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))
            out.append({
                "name": m["name"], "agent": m["agent"], "version": m["version"],
                "open_source": bool(m.get("open_source")),
                "license": m.get("license"), "path": rel,
                "entry": entry, "capabilities": caps,
                "depends_on": [d.get("name") for d in (m.get("depends_on") or [])
                               if isinstance(d, dict)],
                "conflicts": m.get("conflicts") or [],
            })
        except (ManifestError, LoadError) as e:  # noqa: PERF203
            if tolerate:
                print(f"[scan] {root} manifest 校验失败(容错跳过): {e}")
            else:
                raise
    return out


def _try_rel(path, root):
    try:
        rel = os.path.relpath(path, root)
    except ValueError:  # Windows 跨盘无相对路径
        rel = path
    return rel.replace("\\", "/")  # 跨平台：统一正斜杠


def resolve_order(manifests: list) -> list:
    """拓扑排序：被依赖者先加载。Kahn 算法 + 环检测。"""
    names = [m["name"] for m in manifests]
    graph = {}
    indeg = {n: 0 for n in names}
    for m in manifests:
        for dep in m.get("depends_on") or []:
            if dep not in names:
                continue
            # 边指向「依赖者」：被依赖者 indegree 低，先出
            graph.setdefault(dep, []).append(m["name"])
            indeg[m["name"]] += 1
    ready = [n for n in names if indeg[n] == 0]
    order = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in graph.get(n, []):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
    if len(order) != len(names):
        cyc = [n for n in names if indeg[n] > 0]
        raise DependencyCycleError(f"依赖环: {cyc}")
    return order


def check_open_source_boundary(manifests: list) -> None:
    """开源禁依赖闭源：open_source:true 的 depends_on 不得出现 open_source:false。"""
    closed = {m["name"] for m in manifests if not m.get("open_source")}
    for m in manifests:
        if m.get("open_source"):
            for d in m.get("depends_on") or []:
                if d in closed:
                    raise ManifestError(
                        f"开源原子 {m['name']} 依赖闭源原子 {d}（边界铁律）")


class AgentRuntime:
    """统一运行时：注册全部原子 + capability→atom 索引 + 统一路由 + 降级。"""

    def __init__(self, atoms_root: str = DEFAULT_ATOMS_ROOT,
                 registry_path: str = DEFAULT_REGISTRY):
        self.atoms_root = atoms_root
        self.registry_path = registry_path
        self.manifests = []
        self.agents = {}          # name → AtomicAgent 实例
        self._order = []
        self.registry = None

    def scan(self, tolerate: bool = True) -> list:
        self.manifests = scan_atoms(self.atoms_root, tolerate=tolerate)
        return self.manifests

    def load_registry(self) -> dict:
        if os.path.exists(self.registry_path):
            with open(self.registry_path, encoding="utf-8") as f:
                self.registry = json.load(f)
        return self.registry

    def write_registry(self) -> dict:
        data = {"schema": "fde.registry/1.0", "agents": self.manifests}
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.registry = data
        return data

    def resolve(self, names=None):
        """依赖解析：拓扑排序 + 边界。names=None 全量。"""
        manifests = self.manifests
        if names:
            name_set = set(names)
            manifests = [m for m in manifests if m["name"] in name_set]
        check_open_source_boundary(self.manifests)
        self._order = resolve_order(manifests)
        return self._order

    def load(self, names=None, tolerate: bool = True):
        """加载原子（经依赖拓扑序），注册能力。"""
        if not self.manifests:
            self.scan(tolerate=tolerate)
        self.resolve(names)
        # m['path'] 为相对仓库根的路径（scan_atoms 里 _try_rel 基准是仓库根）
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        reg = base.CapabilityRegistry()
        for name in self._order:
            m = next(x for x in self.manifests if x["name"] == name)
            atom_dir = m["path"] if os.path.isabs(m["path"]) else os.path.join(repo_root, m["path"])
            try:
                cls = _load_atom_class(atom_dir, m["entry"])
                inst = cls(name=m["name"], agent=m["agent"], version=m["version"],
                           open_source=m["open_source"], license=m["license"])
                inst.load({"atom_dir": atom_dir})
                inst.register(reg)
                self.agents[name] = inst
            except Exception as e:  # noqa: BLE001
                if not tolerate:
                    raise
                print(f"[load] {name} 加载失败(容错跳过): {e}")
        return self.agents

    def status(self) -> dict:
        return {
            "atoms": [{"name": n, "agent": a.agent, "version": a.version,
                       "open_source": a.open_source, "state": a.state}
                      for n, a in self.agents.items()],
            "order": self._order,
        }

    def capabilities(self) -> dict:
        reg = base.CapabilityRegistry()
        for a in self.agents.values():
            reg.add_many(a.name, a.capabilities())
        return reg.all()

    def provider(self, capability: str) -> str:
        return self.capabilities().get(capability)

    def run_capability(self, capability: str, **inputs) -> dict:
        """统一能力路由：经 capability→atom 索引找到提供原子 → run。"""
        prov = self.provider(capability)
        if not prov:
            return base.fail(f"能力未提供: {capability}")
        agent = self.agents.get(prov)
        if agent is None:
            return base.fail(f"原子未加载: {prov}")
        return agent.run(_capability=capability, **inputs)

    def run_chain(self, steps, **init):
        """组装链：steps=[(capability, kwargs_port_name)...]，上一环 {ok,data} 注入下一环。

        对齐生态 run_flow：把上游 data 写入 data[step] 供下一环 inputs 注入。
        返回 {ok, data:{steps:[...], final}, loop_closed:...}。
        """
        data = dict(init)
        trace = []
        for cap in steps:
            kwargs = {}
            env = self.run_capability(cap, **kwargs)
            trace.append({"capability": cap, "ok": env.get("ok", False),
                          "error": env.get("error"), "data": env.get("data")})
            if env.get("ok"):
                data[cap] = env.get("data")
        return base.ok({"steps": trace, "final": data})

    # ---- 组装链 run_flow：装配文件驱动，前一环输出=后一环输入 ----
    @staticmethod
    def _ref_path(path, ctx):
        """解析 '$ref: step_id.path.to.key'。支持 list[dict] 映射提取。"""
        parts = path.split(".")
        sid = parts[0]
        if sid not in ctx:
            return None
        node = ctx[sid]
        for p in parts[1:]:
            if isinstance(node, list):
                if node and isinstance(node[0], dict) and p in node[0]:
                    node = [x.get(p) for x in node]
                else:
                    return None
            elif isinstance(node, dict):
                node = node.get(p)
            else:
                return None
        return node

    def _resolve_value(self, v, ctx, workdir):
        """递归解析输入值：'$dir'→共享目录；dict{'$ref':...}→取上游输出；'${...}'→模板插值。"""
        if isinstance(v, dict) and "$ref" in v:
            return self._ref_path(v["$ref"], ctx)
        if isinstance(v, str):
            if v == "$dir":
                return workdir
            if "${" in v:
                import re
                def _repl(m):
                    val = self._ref_path(m.group(1), ctx)
                    return "" if val is None else str(val)
                return re.sub(r"\$\{([^}]+)\}", _repl, v)
            return v
        if isinstance(v, list):
            return [self._resolve_value(x, ctx, workdir) for x in v]
        if isinstance(v, dict):
            return {k: self._resolve_value(x, ctx, workdir)
                    for k, x in v.items()}
        return v

    def run_flow(self, assembly: dict, workdir: str = None) -> dict:
        """装配链 run_flow：按 steps 顺序逐原子 run，上游 {ok,data} 注入下游端口。

        assembly: {"name","steps":[{"id","capability","op","inputs":{...},
                   "when":{...},"optional":bool}], "final":{...}}
        - inputs 里的 '$dir' 指共享工作目录；'$ref: step_id.path' 引用前一环输出。
        - 'when': 条件步骤（schema 2.0），仅当条件满足才执行，否则标记 skipped。
            形如 {"$ref":"predict.risk.level","in":["high","critical"]} 或
            {"$ref":"...","equals":val} 或真值（truthy）。
        - 'optional': 可选步骤，能力未提供/步骤失败时降级跳过，链不崩溃（如闭源 deliver.accept）。
        - 'final': 由装配 final 的 $ref 聚合（优先），否则 _flow_final 按能力聚合。
        输出 {ok, data:{steps:[trace], final}, loop_closed}。
        """
        import tempfile
        if workdir is None:
            workdir = assembly.get("dir") or tempfile.mkdtemp(prefix="fde_flow_")
        ctx = {"dir": workdir}
        trace = []
        for step in assembly.get("steps", []):
            sid = step.get("id", step.get("capability"))
            cap = step.get("capability")
            op = step.get("op")
            # ---- when 条件步骤判定 ----
            if step.get("when") is not None:
                skip_reason = self._when_skip(step["when"], ctx)
                if skip_reason:
                    trace.append({"id": sid, "capability": cap, "op": op,
                                  "ok": False, "skipped": True,
                                  "error": skip_reason, "data": None})
                    continue
            raw = step.get("inputs") or {}
            kwargs = {k: self._resolve_value(v, ctx, workdir)
                      for k, v in raw.items()}
            kwargs.setdefault("op", op)
            env = self.run_capability(cap, **kwargs)
            rec = {"id": sid, "capability": cap, "op": op,
                   "ok": env.get("ok", False), "error": env.get("error"),
                   "data": env.get("data")}
            # ---- optional 步骤降级：失败/缺能力 → 标记 skipped，不崩链 ----
            if not env.get("ok") and step.get("optional"):
                rec["skipped"] = True
                rec["degraded"] = True
                rec["error"] = (rec.get("error") or "可选步骤降级跳过")
                trace.append(rec)
                continue
            trace.append(rec)
            if env.get("ok"):
                ctx[sid] = env.get("data")
        final = self._flow_final(assembly, trace, ctx)
        closed = all(t.get("ok") for t in trace)
        loop_closed = bool(final.get("accept")) and closed
        return base.ok({"steps": trace, "final": final}) | {"loop_closed": loop_closed}

    @staticmethod
    def _when_skip(cond, ctx) -> str:
        """when 条件判定：返回跳过原因(str)或 None(满足，执行)。"""
        if not isinstance(cond, dict):
            return None if cond else "when 条件为假"
        val = cond.get("$ref")
        if val is not None:
            resolved = AgentRuntime._ref_path(val, ctx)
        else:
            resolved = cond.get("value")
        in_list = cond.get("in")
        if in_list is not None:
            return None if resolved in in_list else \
                f"when 不满足: {val}={resolved} ∉ {in_list}"
        equals = cond.get("equals")
        if equals is not None:
            return None if resolved == equals else \
                f"when 不满足: {val}={resolved} != {equals}"
        return None if resolved else f"when 不满足: {val}={resolved}"

    @staticmethod
    def _flow_final(assembly, trace, ctx=None):
        """汇总 final。优先取装配 'final' 的 $ref 聚合；否则按能力启发式聚合。"""
        ctx = ctx or {}
        asm_final = assembly.get("final")
        if isinstance(asm_final, dict) and asm_final:
            out = {}
            for k, v in asm_final.items():
                out[k] = AgentRuntime._resolve_ref(v, ctx)
            # 未显式声明的标准字段兜底
            out.setdefault("worst_level", "ok")
            out.setdefault("tickets", [])
            out.setdefault("accept", False)
            return out
        # 启发式聚合（无 final 字段时）
        worst = "ok"
        tickets = []
        report = None
        accept = False
        for t in trace:
            if not t["ok"]:
                worst = "error"
            d = t.get("data") or {}
            if t["capability"] == "monitor.device":
                al = d.get("alerts")
                if al:
                    worst = "critical" if any(a.get("level") == "critical"
                                              for a in al) else "warn"
            if t["capability"] == "fde.task":
                tk = d.get("ticket")
                if isinstance(tk, dict):
                    tid = tk.get("id")
                    if tid is not None:
                        tickets = [x for x in tickets if x.get("id") != tid]
                    tickets.append(tk)
            if t["capability"] == "deliver.accept":
                pkg = d.get("package") or {}
                report = pkg.get("report")
                acc = pkg.get("acceptance") or d.get("accept") or {}
                lst = acc.get("acceptance_list") or []
                accept = bool(lst) and all(x.get("pass") or x.get("result") == "通过"
                                           for x in lst)
        return {"worst_level": worst, "tickets": tickets, "report": report,
                "accept": accept}

    @staticmethod
    def _resolve_ref(v, ctx):
        """解析 final 里的值：dict{'$ref':...} → 取上游；'${...}'/'|len' 模板。"""
        if isinstance(v, dict) and "$ref" in v:
            ref = v["$ref"]
            if isinstance(ref, str) and ref.endswith("|len"):
                base = AgentRuntime._ref_path(ref[:-4], ctx)
                return len(base) if isinstance(base, (list, dict)) else 0
            return AgentRuntime._ref_path(ref, ctx)
        if isinstance(v, str):
            import re
            if v.endswith("|len"):
                base = AgentRuntime._ref_path(v[:-4], ctx)
                return len(base) if isinstance(base, (list, dict)) else 0
            if "${" in v:
                def _repl(m):
                    val = AgentRuntime._ref_path(m.group(1), ctx)
                    return "" if val is None else str(val)
                return re.sub(r"\$\{([^}]+)\}", _repl, v)
            if v == "$dir":
                return ctx.get("dir")
            return v
        if isinstance(v, list):
            return [AgentRuntime._resolve_ref(x, ctx) for x in v]
        if isinstance(v, dict):
            return {k: AgentRuntime._resolve_ref(x, ctx) for k, x in v.items()}
        return v

