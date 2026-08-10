# -*- coding: utf-8 -*-
"""visualize.py — 数据可视化（matplotlib，本机已装）。

数据分析结果出图：SPC 控制图（UCL/LCL/失控点）/ 趋势图 / 异常标记。
依赖 matplotlib；不可用时明确报错（可降级）。

输出 PNG 到指定目录（默认 ~/.solo/charts/），返回文件路径。
"""
from __future__ import annotations

import os

try:
    import matplotlib
    matplotlib.use("Agg")  # 无界面后端，适合服务端/CLI
    import matplotlib.pyplot as plt
    # 中文字体（Windows 微软雅黑 / SimHei；缺失时回退，避免中文变方块）
    try:
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass
    _MPL = True
except ImportError:
    _MPL = False


def _out_dir() -> str:
    d = os.environ.get("SOLO_CHARTS", os.path.expanduser("~/.solo/charts"))
    os.makedirs(d, exist_ok=True)
    return d


def _require_mpl():
    if not _MPL:
        raise RuntimeError("matplotlib 未安装（可选依赖），无法出图。请 pip install matplotlib")


def spc_chart(data: list, title: str = "SPC 控制图", x_labels: list = None,
              filename: str = "spc") -> dict:
    """SPC 控制图：均值线 + UCL/LCL + 失控点标红。

    data: 数值序列
    title: 图标题
    x_labels: x 轴标签（可选）
    filename: 输出文件名（不含扩展名）
    """
    _require_mpl()
    if not data:
        return {"ok": False, "error": "无数据"}
    import statistics
    n = len(data)
    mean = statistics.mean(data)
    stdev = statistics.stdev(data) if n > 1 else 0
    ucl = mean + 3 * stdev
    lcl = mean - 3 * stdev

    fig, ax = plt.subplots(figsize=(10, 5))
    xs = range(n)
    ax.plot(xs, data, "b-o", markersize=4, label="样本")
    ax.axhline(mean, color="g", linestyle="--", label=f"均值 {mean:.2f}")
    ax.axhline(ucl, color="r", linestyle="--", label=f"UCL {ucl:.2f}")
    ax.axhline(lcl, color="r", linestyle="--", label=f"LCL {lcl:.2f}")
    # 失控点（超出 UCL/LCL）标红
    out = [(i, v) for i, v in enumerate(data) if v > ucl or v < lcl]
    if out:
        ax.scatter([i for i, _ in out], [v for _, v in out],
                   color="red", s=80, zorder=5, label=f"失控点 {len(out)}")
    ax.set_title(title)
    ax.set_xlabel("样本序号")
    ax.set_ylabel("数值")
    if x_labels:
        ax.set_xticks(xs)
        ax.set_xticklabels(x_labels, rotation=45, ha="right")
    ax.legend()
    ax.grid(True, alpha=0.3)

    path = os.path.join(_out_dir(), filename + ".png")
    plt.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return {"ok": True, "path": path.replace("\\", "/"),
            "mean": round(mean, 2), "ucl": round(ucl, 2), "lcl": round(lcl, 2),
            "out_of_control": len(out)}


def trend_chart(data: list, title: str = "趋势图", x_labels: list = None,
                filename: str = "trend", anomaly_indices: list = None) -> dict:
    """趋势图：时间序列趋势 + 可选异常点标红。

    data: 数值序列
    anomaly_indices: 异常点下标列表（可选，标红）
    """
    _require_mpl()
    if not data:
        return {"ok": False, "error": "无数据"}
    fig, ax = plt.subplots(figsize=(10, 4))
    xs = range(len(data))
    ax.plot(xs, data, "b-", linewidth=1.5)
    ax.fill_between(xs, data, alpha=0.1, color="blue")
    if anomaly_indices:
        ax.scatter([i for i in anomaly_indices if i < len(data)],
                   [data[i] for i in anomaly_indices if i < len(data)],
                   color="red", s=80, zorder=5, label=f"异常 {len(anomaly_indices)}")
    ax.set_title(title)
    if x_labels:
        ax.set_xticks(xs)
        ax.set_xticklabels(x_labels, rotation=45, ha="right")
    ax.legend()
    ax.grid(True, alpha=0.3)
    path = os.path.join(_out_dir(), filename + ".png")
    plt.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return {"ok": True, "path": path.replace("\\", "/")}


def anomaly_chart(data: list, anomalies: list, title: str = "异常检测",
                  filename: str = "anomaly") -> dict:
    """异常检测图：标出所有异常点。

    data: 数值序列
    anomalies: [{"index": i, "value": v}, ...] 异常点列表（stats.detect_anomaly 输出）
    """
    idxs = [a.get("index") for a in anomalies if "index" in a]
    return trend_chart(data, title, filename=filename, anomaly_indices=idxs)
