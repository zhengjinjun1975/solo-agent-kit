# -*- coding: utf-8 -*-
"""manifest.py — 原子 manifest schema 校验。

必填：schema_version / name(==目录名) / agent(类型) / version(语义化) / entry / license / open_source。
可选：provides(能力id) / depends_on(原子依赖) / conflicts / run_config。
校验铁律：开闭源一致性；resources 路径禁逃逸；agent 类型白名单。
"""
from __future__ import annotations

import json
import os
import re

_SCHEMA_VERSION = "agent.manifest/1.0"

# agent 类型白名单（对齐生态：fde/monitor/memory/write/ontology/deliver 等）
VALID_AGENT_TYPES = {
    "fde", "monitor", "memory", "write", "ontology", "deliver",
    "cognition", "rag", "decision", "event", "learning", "codereview",
}

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class ManifestError(Exception):
    """manifest 校验失败。"""


def _check_open_closed(manifest: dict) -> None:
    """开闭源一致性：open_source:false ⇔ license:'closed'。"""
    o = bool(manifest.get("open_source"))
    lic = (manifest.get("license") or "").lower()
    if o and lic == "closed":
        raise ManifestError("open_source:true 但 license='closed' 不一致")
    if not o and lic != "closed":
        raise ManifestError("open_source:false 但 license 非 'closed' 不一致")


def validate(manifest: dict, atom_dir: str = None) -> dict:
    """校验一份 manifest（原 dict 校验；若给 atom_dir 则校验 name==目录名）。"""
    if not isinstance(manifest, dict):
        raise ManifestError("manifest 必须是 dict")
    if manifest.get("schema_version") != _SCHEMA_VERSION:
        raise ManifestError(f"schema_version 须为 {_SCHEMA_VERSION}")
    name = manifest.get("name")
    if not name:
        raise ManifestError("缺少 name")
    if atom_dir and os.path.basename(os.path.abspath(atom_dir)) != name:
        raise ManifestError(f"manifest.name({name}) != 目录名({atom_dir})")
    agent = manifest.get("agent")
    if agent not in VALID_AGENT_TYPES:
        raise ManifestError(f"agent 类型非法: {agent}")
    version = manifest.get("version")
    if not version or not _VERSION_RE.match(version):
        raise ManifestError(f"version 须为语义化 MAJOR.MINOR.PATCH: {version}")
    entry = manifest.get("entry")
    if not entry:
        raise ManifestError("缺少 entry")
    license_v = manifest.get("license")
    if not license_v:
        raise ManifestError("缺少 license")
    if "open_source" not in manifest:
        raise ManifestError("缺少 open_source")
    _check_open_closed(manifest)
    # resources 路径防逃逸
    for r in manifest.get("resources", []) or []:
        p = r.get("path", "")
        if ".." in p or os.path.isabs(p) or re.match(r"^[a-zA-Z]:", p):
            raise ManifestError(f"resources 路径非法(防逃逸): {p}")
    return manifest


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    return validate(m, os.path.dirname(path))
