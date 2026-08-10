# -*- coding: utf-8 -*-
"""site.py — 厂区运维配置与定位（零依赖）。

solo 是带着笔记本进对方厂区的 FDE 工具：
- 本机是操作入口（次要），服务对象是对方厂区局域网设备（主要）
- 维护厂区上下文 + 设备台账（host/user/port），供监控/日志/远程/工单使用
- 支持双部署角色: laptop(笔记本本机) / on-site(部署在对方机)

密码不入库（仅 host/user/port），用系统 SSH key。
"""
from __future__ import annotations

import os

DEFAULT_FILE = os.path.join(os.path.expanduser("~"), ".solo", "site.json")


class Site:
    """厂区配置：role / current_site / sites(含设备台账)。"""

    def __init__(self, file: str = DEFAULT_FILE):
        self.file = file
        os.makedirs(os.path.dirname(file), exist_ok=True)
        self._cfg = self._load()

    # ---- 读取 ----
    def _load(self) -> dict:
        if not os.path.exists(self.file):
            return {"role": "laptop", "current_site": "", "sites": {}}
        import json
        try:
            with open(self.file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"role": "laptop", "current_site": "", "sites": {}}

    def _save(self) -> None:
        from solo.base import atomic_write, lock_for
        with lock_for(self.file):
            atomic_write(self.file, self._cfg)

    # ---- 部署角色 ----
    @property
    def role(self) -> str:
        return self._cfg.get("role", "laptop")

    def set_role(self, role: str) -> dict:
        """设置部署角色: laptop / on-site。"""
        if role not in ("laptop", "on-site"):
            return {"ok": False, "error": "role 只能是 laptop 或 on-site"}
        self._cfg["role"] = role
        self._save()
        return {"ok": True, "role": role}

    # ---- 当前厂区（定位锚点）----
    @property
    def current_site(self) -> str:
        return self._cfg.get("current_site", "")

    def use(self, name: str) -> dict:
        """切换到指定厂区（定位）。"""
        if name not in self._cfg.get("sites", {}):
            return {"ok": False, "error": f"厂区不存在: {name}", "sites": self.list_sites()}
        self._cfg["current_site"] = name
        self._save()
        return {"ok": True, "current_site": name}

    def add_site(self, name: str, location: str = "", contact: str = "") -> dict:
        """新增厂区。"""
        if name in self._cfg.setdefault("sites", {}):
            return {"ok": False, "error": f"厂区已存在: {name}"}
        self._cfg["sites"][name] = {"location": location, "contact": contact, "devices": []}
        if not self._cfg.get("current_site"):
            self._cfg["current_site"] = name
        self._save()
        return {"ok": True, "site": name}

    def list_sites(self) -> list:
        return list(self._cfg.get("sites", {}).keys())

    def site_info(self, name: str = None) -> dict:
        """当前或指定厂区信息（含设备清单）。"""
        name = name or self.current_site
        return self._cfg.get("sites", {}).get(name, {})

    # ---- 设备台账 ----
    def devices(self, site: str = None) -> list:
        """当前/指定厂区的设备台账。"""
        info = self.site_info(site)
        return info.get("devices", []) if info else []

    def add_device(self, name: str, host: str, user: str = "", port: int = 22,
                   group: str = "", role: str = "", site: str = None) -> dict:
        """添加设备到当前/指定厂区。host 必填。"""
        site = site or self.current_site
        if site not in self._cfg.get("sites", {}):
            return {"ok": False, "error": f"厂区不存在: {site}", "sites": self.list_sites()}
        if not host:
            return {"ok": False, "error": "host 必填"}
        devs = self._cfg["sites"][site].setdefault("devices", [])
        if any(d["name"] == name for d in devs):
            return {"ok": False, "error": f"设备已存在: {name}"}
        devs.append({"name": name, "host": host, "user": user,
                     "port": int(port), "group": group, "role": role})
        self._save()
        return {"ok": True, "device": name, "site": site}

    def rm_device(self, name: str, site: str = None) -> dict:
        """移除设备。"""
        site = site or self.current_site
        devs = self._cfg.get("sites", {}).get(site, {}).get("devices", [])
        new = [d for d in devs if d["name"] != name]
        if len(new) == len(devs):
            return {"ok": False, "error": f"设备不存在: {name}"}
        self._cfg["sites"][site]["devices"] = new
        self._save()
        return {"ok": True, "removed": name, "site": site}

    def resolve_device(self, name: str, site: str = None) -> dict:
        """按设备名解析连接信息（供 remote/monitor/logs 用）。"""
        site = site or self.current_site
        for d in self.devices(site):
            if d["name"] == name:
                return {"ok": True, "device": d, "site": site}
        return {"ok": False, "error": f"当前厂区无设备: {name}", "site": site}
