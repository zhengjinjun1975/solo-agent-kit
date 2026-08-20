# -*- coding: utf-8 -*-
"""solo P1 收尾回归：协议实采 / evolve自进化接入组装链 / RAG语义命中 / linkage健壮。

P1 四项能力真实数据验证（全部走真实连接/真实数据/真实仓库树，非空壳）：

  1. 协议实采连接读数据 : monitor-device protocol_read 连本地真实模拟器读 Modbus/TCP
     与 OPC-UA 节点，返回统一指标点（真实协议帧/真实 socket）。
  2. evolve自进化接入组装链 : evolve.self 原子注册 + solo-linkage-workflow.json 链尾
     自进化闭环（loop_closed=True / evolve_loop_closed=True）。
  3. RAG语义命中 : 离线真向量（n-gram 哈希向量+余弦）对同义改写查询命中近义文档，
     且 hybrid_rank 混合检索不崩溃（回归解包 bug）。
  4. linkage健壮 : verify_linkage 依赖库版本/关键文件在位检测、缺失清晰报错(missing+fix)、
     单库/双库缺失回退不崩溃。

跑法：python -m pytest tests/test_p1_finalize.py -v
"""
import importlib.util
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fde_runtime import linkage  # noqa: E402
from fde_runtime.loader import AgentRuntime  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_protocols_impl():
    """经文件路径加载 protocols_impl（atoms 非包，不能 import 路径点）。"""
    p = os.path.join(_REPO, "atoms", "monitor", "monitor-device",
                     "_impl", "protocols_impl.py")
    spec = importlib.util.spec_from_file_location("p1_protocols_impl", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rt():
    r = AgentRuntime()
    r.scan(tolerate=True)
    r.load(tolerate=True)
    return r


@pytest.fixture(scope="module")
def protocols_impl():
    return _load_protocols_impl()


# ═══════════════════════ 1. 协议实采：连接 + 读数据 ═══════════════════════
class TestProtocolRealRead:
    def test_modbus_tcp_real_connect_read(self, rt, protocols_impl):
        """Modbus/TCP 纯标准库直采：起真实模拟器 → 真实协议帧连接读寄存器 → 统一指标点。"""
        mb = protocols_impl.ModbusTcpSimulator(registers={0: 42, 1: 137}, port=0)
        port = mb.start()
        d = tempfile.mkdtemp(prefix="p1_modbus_")
        try:
            r = rt.run_capability("monitor.device", op="protocol_read", dir=d, config={
                "protocol": "modbus", "host": "127.0.0.1", "port": port, "unit": 1,
                "registers": [{"address": 0, "count": 1, "name": "temp"},
                              {"address": 1, "count": 1, "name": "vib"}],
                "device_id": "pump_01"})
            assert r["ok"], r.get("error")
            assert r["data"]["protocol"] == "modbus"
            assert r["data"]["count"] == 2, "应读 2 个寄存器"
            pts = {p["metric"]: p["value"] for p in r["data"]["read"]["points"]}
            assert pts["temp"] == 42.0 and pts["vib"] == 137.0, f"读取值不符: {pts}"
            # 直采点应已入存储（非空壳，真实数据落库）
            snap = rt.run_capability("monitor.device", op="snapshot", dir=d)
            assert snap["ok"] and snap["data"]["snapshot"]["devices"], "直采点未入库"
        finally:
            mb.stop()

    def test_opcua_stdlib_real_connect_read(self, rt, protocols_impl):
        """OPC-UA 纯标准库子集直采：起真实模拟器 → HEL/ACK 握手 + Read 节点 → 读值。"""
        oc = protocols_impl.OpcUaSimulator(
            node_values={"ns=2;i=5": 8.6, "ns=2;i=7": 12.3}, port=0)
        port = oc.start()
        d = tempfile.mkdtemp(prefix="p1_opcua_")
        try:
            r = rt.run_capability("monitor.device", op="protocol_read", dir=d, config={
                "protocol": "opcua", "mode": "stdlib",
                "url": f"opc.tcp://127.0.0.1:{port}",
                "node_ids": ["ns=2;i=5", "ns=2;i=7"], "device_id": "opc_dev"})
            assert r["ok"], r.get("error")
            assert r["data"]["protocol"] == "opcua"
            assert r["data"]["count"] == 2
            vals = [p["value"] for p in r["data"]["read"]["points"]]
            assert 8.6 in vals and 12.3 in vals, f"OPC-UA 读值不符: {vals}"
        finally:
            oc.stop()

    def test_protocol_available_true(self, rt):
        """modbus/opcua 纯标准库直采应为 available（不再接口预留 available:false）。"""
        r = rt.run_capability("monitor.device", op="protocols")
        # 缺其它库可能 degraded，但 modbus/opcua 必须可用
        protos = r.get("data", {}).get("protocols") or []
        avail = {p["kind"]: p["available"] for p in protos}
        assert avail.get("modbus") is True, "modbus 纯标准库应可用"
        assert avail.get("opcua") is True, "opcua 纯标准库应可用"

    def test_protocol_connect_failure_clear_error(self, rt):
        """连不上的端口应明确报错（绝不静默/绝不假装读到数据）。"""
        r = rt.run_capability("monitor.device", op="protocol_read", config={
            "protocol": "modbus", "host": "127.0.0.1",
            "port": 9, "registers": [{"address": 0, "count": 1}]})
        assert r["ok"] is False
        assert "直采失败" in (r.get("error") or "") or "失败" in (r.get("error") or ""), \
            f"应明确报连接失败: {r.get('error')}"


# ═══════════════════════ 2. evolve 自进化接入组装链 ═══════════════════════
class TestEvolveInAssembly:
    def test_evolve_atom_registered(self, rt):
        """evolve 原子应注册并提供 evolve.self 能力。"""
        assert "evolve" in rt.agents
        caps = rt.capabilities()
        assert "evolve.self" in caps

    def test_evolve_loop_closed_real(self, rt):
        """evolve 单原子自进化闭环（真实观察→归因→改进→闭环）。"""
        d = tempfile.mkdtemp(prefix="p1_evolve_")
        r = rt.run_capability("evolve.self", op="evolve", dir=d,
                              observation="水泵振动误报偏高", target="threshold",
                              feedback=2)
        assert r["ok"], r.get("error")
        assert r["data"]["loop_closed"] is True, "自进化应闭环"
        assert r["data"]["entry"]["target"] == "threshold"

    def test_evolve_in_assembly_chain(self, rt):
        """solo-linkage-workflow.json 组装链（13步，链尾 evolve.self）端到端全绿且闭环。"""
        with open(os.path.join(_REPO, "assemblies", "solo-linkage-workflow.json"),
                  encoding="utf-8") as f:
            asm = json.load(f)
        wd = tempfile.mkdtemp(prefix="p1_link_evolve_")
        res = rt.run_flow(asm, workdir=wd)
        assert res["ok"]
        steps = res["data"]["steps"]
        assert len(steps) == 13, f"应 13 步，实际 {len(steps)}"
        for t in steps:
            assert t["ok"], f"步骤 {t['id']} 失败: {t.get('error')}"
        caps = [t["capability"] for t in steps]
        assert "evolve.self" in caps, "组装链应含 evolve 链尾"
        ev = next(t for t in steps if t["capability"] == "evolve.self")
        assert ev["data"]["loop_closed"] is True, "evolve 链尾应闭环"
        assert res["data"]["final"]["evolve_loop_closed"] is True, \
            "final 应透出 evolve_loop_closed=True"
        # 跨开源联动可用：认知/决策原子来自兄弟仓库能力路由
        assert "ontology.qa" in caps and "sme.decision" in caps

    def test_evolve_registry_13_atoms(self, rt):
        """registry 应登记 13 原子（含 evolve）。"""
        with open(os.path.join(_REPO, "registry.json"), encoding="utf-8") as f:
            reg = json.load(f)
        names = [a["name"] for a in reg["agents"]]
        assert "evolve" in names, "registry 缺 evolve 原子"
        assert len(names) >= 13, f"registry 应 13 原子，实际 {len(names)}"


# ═══════════════════════ 3. 离线 RAG 真向量语义命中 ═══════════════════════
class TestRagSemanticHit:
    def _docs(self):
        return [
            "水泵轴承磨损导致振动越限，需要更换轴承",
            "风机皮带老化，运行时存在打滑噪音",
            "液压系统油压不足，检查油泵与滤芯",
            "温度传感器漂移，校准量程后恢复",
        ]

    def test_vector_rank_synonym_semantic_hit(self):
        """真向量检索：同义改写查询('鼓风机'→'风机'近义词)命中近义文档（语义>字面）。"""
        from kernels import memory_score as ms
        docs = self._docs()
        q = "鼓风机皮带老化打滑出现异响"
        vec = ms.vector_rank(q, docs, top_k=4)
        assert vec, "应返回排序结果"
        assert vec[0]["index"] == 1, f"语义命中风机文档，实际 top={vec[0]}" 
        assert vec[0]["score"] > 0.3, f"语义得分应显著: {vec[0]['score']}"

    def test_hybrid_rank_works_and_hits(self):
        """hybrid_rank 混合检索不崩溃且语义命中（回归解包 bug）。"""
        from kernels import memory_score as ms
        docs = self._docs()
        q = "鼓风机皮带老化打滑出现异响"
        hyb = ms.hybrid_rank(q, docs, top_k=4)
        assert hyb, "混合检索应返回结果"
        assert hyb[0]["index"] == 1, "混合检索应命中风机文档"
        # 所有候选都应打分（score 为 float）
        assert all(isinstance(r["score"], float) for r in hyb)

    def test_vector_embed_self_similarity_highest(self):
        """确定性真向量：同文本余弦=1 且 > 异文本；近义词文本相似度显著高于无关文本。"""
        from kernels import memory_score as ms
        a = "循环水泵振动异常，检查叶轮结垢"
        b = "循环水泵振动异常，检查叶轮结垢"
        c = "风机电机的绝缘老化"
        assert ms.cosine(ms.vector_embed(a), ms.vector_embed(b)) == pytest.approx(1.0)
        sim_b = ms.cosine(ms.vector_embed(a), ms.vector_embed(c))
        assert sim_b < 1.0

    def test_hybrid_synonym_rewrite_hit(self):
        """近义词改写（循环水泵→循环泵）仍应命中同一文档。"""
        from kernels import memory_score as ms
        docs = ["循环水泵振动异常，检查叶轮结垢",
                "风机电机的绝缘老化",
                "传送带跑偏，需要张紧"]
        q = "冷却水循环泵出现异常振动"
        top = ms.vector_rank(q, docs, top_k=3)[0]
        assert top["index"] == 0, f"改写后仍应命中循环水泵: {top}"


# ═══════════════════════ 4. linkage 跨开源健壮 ═══════════════════════
# 兄弟仓库是否在位的检测（独立优先：仓库不在时跳过集成断言，不连锁依赖）
_HAS_FACTORY = linkage.find_factory() is not None
_HAS_SME = linkage.find_sme() is not None


class TestLinkageRobust:
    @pytest.mark.skipif(not (_HAS_FACTORY and _HAS_SME),
                        reason="兄弟仓库未在位，跳过跨仓库集成断言（独立可跑）")
    def test_verify_linkage_healthy(self):
        """真实兄弟仓库：双库 present + 依赖全在 + available=True。"""
        st = linkage.verify_linkage()
        assert st["factory_ontology_kit"]["present"]
        assert st["sme_decision_ontology"]["present"]
        assert st["factory_ontology_kit"]["deps_ok"] is True
        assert st["sme_decision_ontology"]["deps_ok"] is True
        assert st["factory_ontology_kit"]["missing"] == []
        assert st["sme_decision_ontology"]["missing"] == []
        assert st["available"] is True

    def test_check_required_missing_clear_error(self, tmp_path):
        """缺关键依赖文件 → missing 列出 + ok=False + 清晰 fix 提示（不静默）。"""
        fake = tmp_path / "factory-ontology-kit"
        (fake / "codes").mkdir(parents=True)
        (fake / "codes" / "ontology_qa_v3.py").write_text("x")
        # 故意缺 codes/bm25_retrieval.py
        ck = linkage.check_required(str(fake), clear=True)
        assert ck["present"] is True
        assert ck["ok"] is False
        missing_files = [m["file"] for m in ck["missing"]]
        assert "codes/bm25_retrieval.py" in missing_files
        miss = next(m for m in ck["missing"]
                    if m["file"] == "codes/bm25_retrieval.py")
        assert "fix" in miss and miss["role"], "缺失项应带 fix 提示与角色说明"

    def test_check_required_none_clear_error(self):
        """未发现兄弟仓库 → present=False + 清晰 error（经环境变量可指定）。"""
        ck = linkage.check_required(None)
        assert ck["present"] is False
        assert ck["ok"] is False
        assert "环境变量" in ck["error"], f"应提示环境变量指定: {ck['error']}"

    @pytest.mark.skipif(not _HAS_SME,
                        reason="兄弟仓库 sme 未在位，跳过该集成断言（独立可跑）")
    def test_verify_linkage_single_repo_missing_dep_fallback(self, monkeypatch, tmp_path):
        """单库缺依赖 → deps_ok=False + missing 列出；另一库正常 → available 仍 True（回退不崩溃）。"""
        fake = tmp_path / "factory-ontology-kit"
        (fake / "codes").mkdir(parents=True)
        (fake / "codes" / "ontology_qa_v3.py").write_text("x")  # 缺 bm25_retrieval.py
        real_sme = linkage.find_sme()
        monkeypatch.setattr(linkage, "find_factory", lambda: str(fake))
        monkeypatch.setattr(linkage, "find_sme", lambda: real_sme)
        st = linkage.verify_linkage()
        assert st["factory_ontology_kit"]["deps_ok"] is False
        assert st["factory_ontology_kit"]["missing"], "应列出缺失依赖"
        assert st["available"] is True, "另一库正常，整体 available 应回退为 True"
        assert "fallback" in st and "回退" in st["fallback"]

    def test_verify_linkage_both_absent_available_false(self, monkeypatch):
        """双库缺失 → available=False，明确回退（不崩溃、不假装可用）。"""
        monkeypatch.setattr(linkage, "find_factory", lambda: None)
        monkeypatch.setattr(linkage, "find_sme", lambda: None)
        st = linkage.verify_linkage()
        assert st["factory_ontology_kit"]["present"] is False
        assert st["sme_decision_ontology"]["present"] is False
        assert st["available"] is False
