#!/usr/bin/env python3
"""install_deps.py — 进厂部署可选依赖安装。

核心零依赖运行时，仅企业级能力需要可选驱动：
  MySQL      → pymysql          （企业台账接入）
  Postgres   → psycopg2-binary  （企业台账接入）
  监控增强   → psutil           （环境监控完整版，缺省降级）

用法：
  python scripts/install_deps.py           # 安装全部可选
  python scripts/install_deps.py --mysql   # 仅 MySQL
  python scripts/install_deps.py --pg      # 仅 Postgres
"""
import subprocess
import sys

# 可选依赖: [flag, pip 包名, 用途]
OPTIONAL = [
    ("--mysql", "pymysql", "MySQL 企业台账接入"),
    ("--pg", "psycopg2-binary", "Postgres 企业台账接入"),
    ("--psutil", "psutil", "环境监控完整版(缺省降级)"),
]


def main():
    args = sys.argv[1:]
    install_all = not any(a in ("--mysql", "--pg", "--psutil") for a in args)
    installed = 0
    for flag, pkg, use in OPTIONAL:
        if install_all or flag in args:
            print(f"[安装] {pkg} — {use} ...", end=" ", flush=True)
            r = subprocess.run([sys.executable, "-m", "pip", "install", pkg],
                               capture_output=True, text=True)
            if r.returncode == 0:
                print("✅")
                installed += 1
            else:
                print(f"❌ {r.stderr.strip()[-150:]}")
    print(f"\n完成: 安装 {installed} 个可选依赖")
    if not install_all:
        print("提示: 核心能力(CSV/SQLite/本体/决策)零依赖，无需安装即可用")


if __name__ == "__main__":
    main()
