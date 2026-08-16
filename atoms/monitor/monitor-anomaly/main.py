# -*- coding: utf-8 -*-
"""monitor-anomaly 原子：FDE 监测深度补强（参考 fde-latest-tech-deepdive §2.2 层1 统计基线）。

在「动态阈值」(monitor-alert 已做)之上，补三类时序异常检测 + 预测性维护雏形，全为
纯标准库、离线可算、真实数学，非空壳：

  - detect/trend        趋势漂移：线性回归斜率(归一化)超阈值 → 缓慢恶化告警
  - detect/sudden_change 突跳/突变：窗口稳健基线(MAD)上最近点 z-score 超阈值 → 突变告警
  - detect/multivariate 多变量：最近窗口均值相对基线的马氏距离(Mahalanobis)超阈值 → 关联异常
  - predict             预测性维护雏形：退化时序线性投影 → 剩余寿命 RUL + 健康指数

API：
  detect(values|series, mode=trend|sudden|multivariate, k=3.0, window=20)
  predict(values, failure_threshold, k=3.0)
"""
from __future__ import annotations
import math
import os
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402


def _vec(series):
    """统一入参：values 列表 或 [{'value':..}] 列表 → 数值列表。"""
    if not series:
        return []
    if isinstance(series[0], (int, float)):
        return [float(x) for x in series]
    out = []
    for it in series:
        if isinstance(it, dict):
            v = it.get("value")
            if v is None:
                continue
            out.append(float(v))
        elif isinstance(it, (int, float)):
            out.append(float(it))
    return out


def _linreg(y):
    """最小二乘线性回归 → {slope, intercept, r}。"""
    n = len(y)
    if n < 2:
        return None
    x = list(range(n))
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx == 0:
        return None
    slope = sxy / sxx
    intercept = my - slope * mx
    var_y = sum((yi - my) ** 2 for yi in y)
    if var_y == 0:
        r = 0.0
    else:
        ss_res = sum((y[i] - (slope * x[i] + intercept)) ** 2 for i in range(n))
        r = math.sqrt(max(0.0, 1.0 - ss_res / var_y))
    return {"slope": slope, "intercept": intercept, "r": r}


def _mad(values):
    med = statistics.median(values)
    mad = statistics.median([abs(v - med) for v in values])
    # MAD 为 0（平坦/多数重合）时回退到 stdev；仍为 0（全相等）则用极小值兜底，避免除零误崩
    scale = mad
    if scale <= 0:
        try:
            scale = statistics.stdev(values) if len(values) > 1 else 1e-9
        except Exception:  # noqa: BLE001
            scale = 1e-9
    return med, (scale if scale > 0 else 1e-9)


def detect_trend(values, k=0.8, window=20, min_r=0.6):
    """趋势漂移：斜率相对区间归一化 + 线性拟合度门槛。

    归一化斜率 slope_norm = |slope|*len/scale（趋势在整个窗口跨度中所占比例）。
    同时要求 |r| ≥ min_r（确为单向线性漂移，而非噪声抖动）。
    纯平坦噪声序列 slope_norm≈0 或 r 小，不误报。
    """
    vals = _vec(values)
    if len(vals) < 4:
        return {"anomaly": False, "note": "数据不足(<4)"}
    reg = _linreg(vals)
    if reg is None:
        return {"anomaly": False, "note": "无法回归"}
    scale = (max(vals) - min(vals)) or 1e-9
    slope_norm = abs(reg["slope"]) / (scale / len(vals))
    strong_fit = abs(reg["r"]) >= min_r
    return {"anomaly": bool(slope_norm > k and strong_fit), "type": "trend",
            "slope": round(reg["slope"], 4), "slope_norm": round(slope_norm, 3),
            "r": round(reg["r"], 3), "k": k}


def detect_sudden(values, k=3.0, window=10):
    """突跳/突变：最近点 vs 窗口稳健基线(MAD) z-score 超阈值。"""
    vals = _vec(values)
    if len(vals) < 4:
        return {"anomaly": False, "note": "数据不足(<4)"}
    baseline = vals[:-1]
    med, scale = _mad(baseline)
    last = vals[-1]
    z = (last - med) / scale
    return {"anomaly": bool(abs(z) > k), "type": "sudden_change",
            "last": last, "baseline": round(med, 3), "z": round(z, 3), "k": k}


def _mahalanobis(point, mean, cov_inv):
    d = [point[i] - mean[i] for i in range(len(point))]
    s = 0.0
    for i in range(len(d)):
        for j in range(len(d)):
            s += d[i] * d[j] * cov_inv[i][j]
    return math.sqrt(max(0.0, s))


def _inverse(mat, eps=1e-6):
    """高斯消元矩阵求逆（返回 None 若奇异）。"""
    n = len(mat)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)]
         for i, row in enumerate(mat)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < eps:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        invp = a[col][col]
        for j in range(2 * n):
            a[col][j] /= invp
        for r in range(n):
            if r == col:
                continue
            fac = a[r][col]
            if abs(fac) < eps:
                continue
            for j in range(2 * n):
                a[r][j] -= fac * a[col][j]
    return [row[n:] for row in a]


def detect_multivariate(series, k=3.0, window=10):
    """多变量：最近窗口均值相对基线窗口均值的马氏距离超阈值 → 多变量联动异常。

    series: {metric_name: [values...]}（各指标对齐）。
    """
    if not isinstance(series, dict) or len(series) < 2:
        return {"anomaly": False, "note": "需≥2个对齐指标"}
    cols = []
    names = list(series.keys())
    for nm in names:
        v = _vec(series[nm])
        if len(v) < 4:
            return {"anomaly": False, "note": f"指标 {nm} 数据不足"}
        cols.append(v)
    n = min(len(c) for c in cols)
    cols = [c[-n:] for c in cols]
    base = [c[:max(1, n - window)] for c in cols]
    recent = [c[-window:] for c in cols]
    bmean = [sum(b) / len(b) if b else 0.0 for b in base]
    rmean = [sum(r) / len(r) if r else 0.0 for r in recent]
    # 基线协方差 + 正则化
    m = len(bmean)
    cov = [[0.0] * m for _ in range(m)]
    nb = len(base[0])
    for t in range(nb):
        row = [base[i][t] - bmean[i] for i in range(m)]
        for i in range(m):
            for j in range(m):
                cov[i][j] += row[i] * row[j]
    cov = [[cov[i][j] / max(1, nb - 1) + (0.01 if i == j else 0.0) for j in range(m)]
           for i in range(m)]
    cinv = _inverse(cov)
    if cinv is None:
        return {"anomaly": False, "note": "协方差奇异，无法马氏距离"}
    md = _mahalanobis(rmean, bmean, cinv)
    return {"anomaly": bool(md > k), "type": "multivariate",
            "mahalanobis": round(md, 3), "k": k, "metrics": names}


def predict_rul(values, failure_threshold, k=3.0):
    """预测性维护雏形：退化时序线性投影 → 剩余寿命 RUL + 健康指数。

    健康指数 = clamp(1 - (current/|threshold|)，退化到阈值 → 0)。
    返回 {rul, health_index, slope, current, threshold, projected}。
    """
    vals = _vec(values)
    if len(vals) < 4:
        return {"rul": None, "note": "数据不足(<4)"}
    reg = _linreg(vals)
    if reg is None:
        return {"rul": None, "note": "无法回归"}
    slope = reg["slope"]
    cur = vals[-1]
    remaining = failure_threshold - cur
    if slope > 0:
        rul = remaining / slope if slope != 0 else float("inf")
    else:
        rul = None  # 未恶化（斜率不朝阈值方向）
    hi = max(0.0, min(1.0, 1.0 - abs(cur) / max(abs(failure_threshold), 1e-9)))
    return {"rul": round(rul, 2) if rul is not None and rul != float("inf") else
            ("inf" if rul == float("inf") else None),
            "health_index": round(hi, 3), "slope": round(slope, 4),
            "current": cur, "threshold": failure_threshold,
            "projected_remaining": round(remaining, 3)}


class MonitorAnomalyAtom(AtomicAgent):
    def capabilities(self):
        return ["monitor.anomaly"]

    def _run(self, op: str = "detect", **params):
        values = params.get("values")
        series = params.get("series") or params.get("multivariate_series")
        if op == "detect":
            mode = params.get("mode", "sudden")
            # k 阈值按模式默认：sudden/multivariate 用 z-score 阈值 3.0，
            # trend 用归一化斜率阈值 0.8（未显式传 k 时用模式各自默认，避免误用）
            k = params.get("k")
            if mode == "trend":
                if not values:
                    return fail("trend 需 values")
                return ok(detect_trend(values, k=k if k is not None else 0.8))
            if mode == "multivariate":
                if not series:
                    return fail("multivariate 需 series={metric:[值...]}")
                return ok(detect_multivariate(series, k=k if k is not None else 3.0))
            # default sudden / sudden_change
            if not values:
                return fail("sudden 需 values")
            return ok(detect_sudden(values, k=k if k is not None else 3.0))
        if op == "predict":
            values = params.get("values") or params.get("degradation")
            ft = params.get("failure_threshold")
            if not values or ft is None:
                return fail("predict 需 values + failure_threshold")
            return ok(predict_rul(values, float(ft)))
        return fail(f"未知 op: {op}")


def _main():
    a = MonitorAnomalyAtom(name="monitor-anomaly", agent="monitor", version="0.1.0")
    a.load()
    # 趋势漂移：缓慢爬升应触发
    trend = [10.0 + 0.5 * i + (i % 3) * 0.1 for i in range(30)]
    r = a.run(op="detect", mode="trend", values=trend, k=0.8)
    assert r.get("ok") and r["data"]["anomaly"], "趋势漂移应触发"
    print("  trend 触发:", r["data"]["slope_norm"])
    # 突跳：稳态 + 极端突跳应触发
    steady = [10.0 + (i % 3) * 0.1 for i in range(20)] + [30.0]
    r2 = a.run(op="detect", mode="sudden", values=steady, k=3.0)
    assert r2.get("ok") and r2["data"]["anomaly"], "突跳应触发"
    print("  sudden z:", r2["data"]["z"])
    # 多变量：两指标本应相关，但近期 temp 突升破坏了关联 → 马氏距离大 → 触发
    mv = {"vibration": [5.0 + (i % 2) * 0.1 for i in range(30)],
          "temp": [50.0 + (10.0 if i >= 25 else 0.0) for i in range(30)]}
    r3 = a.run(op="detect", mode="multivariate", series=mv, k=3.0)
    assert r3.get("ok") and r3["data"]["anomaly"], "多变量关联破坏应触发"
    print("  multivariate mahalanobis:", r3["data"]["mahalanobis"])
    # 相关共升（同方向漂移）应视为正常关联，不误报
    mv_ok = {"vibration": [5.0 + 0.2 * i for i in range(30)],
             "temp": [50.0 + 1.0 * i for i in range(30)]}
    r3b = a.run(op="detect", mode="multivariate", series=mv_ok, k=3.0)
    assert r3b.get("ok") and not r3b["data"]["anomaly"], "相关共升不应误报"
    print("  correlated-同升 不误报:", r3b["data"]["mahalanobis"])
    # 预测性维护：线性退化投影出 RUL
    deg = [5.0 + 0.3 * i for i in range(40)]  # 当前 ~16.7，阈值 20
    r4 = a.run(op="predict", values=deg, failure_threshold=20.0)
    assert r4.get("ok") and r4["data"]["rul"] is not None, "RUL 应可预测"
    print("  predict RUL:", r4["data"]["rul"], "health:", r4["data"]["health_index"])
    print("monitor-anomaly 独立自测通过, 0 失败")


if __name__ == "__main__":
    _main()
