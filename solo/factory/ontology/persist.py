# -*- coding: utf-8 -*-
"""persist.py — Ontology 持久化职责：save / load（JSON）。"""
from __future__ import annotations

import json

# (plain mixin, no _Core inheritance)


class _PersistMixin:
    # ---- 持久化 ----
    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"entities": self.entities, "relations": self.relations,
                       "triples": self.triples}, f, ensure_ascii=False)

    def load(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.entities, self.relations = d["entities"], d["relations"]
        self.triples = d["triples"]
