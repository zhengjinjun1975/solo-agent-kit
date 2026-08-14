# -*- coding: utf-8 -*-
"""retrieve.py — Ontology 检索职责：search。"""
from __future__ import annotations

# (plain mixin, no _Core inheritance)


class _RetrieveMixin:
    # ---- 检索 ----
    def search(self, term: str, top_k: int = 5) -> list:
        t = term.strip().lower()
        hits = [(s, p, o) for s, p, o in self.triples
                if t in s.lower() or t in p.lower() or t in o.lower()]
        return hits[:top_k]
