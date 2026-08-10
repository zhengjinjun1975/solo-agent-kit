# -*- coding: utf-8 -*-
"""example_06_factory_data.py — 工厂现场数据套件（FDE 辅助核心）。

展示工厂现场数据处理完整闭环：
清洗(缺失/重复/异常值) → 分析(描述/趋势) → 异常检测(SPC控制图) → 本体建模。

跑法：python examples/example_06_factory_data.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo.factory import clean as clean_mod
from solo.factory import stats as stats_mod

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def main():
    print("== 场景⑥：工厂现场数据套件（清洗→分析→异常检测） ==\n")

    # 1. 数据清洗
    print("[1/4] 数据清洗...")
    cl = clean_mod.DataCleaner()
    raw = cl.load_csv(os.path.join(DATA, "factory_sensor.csv"))
    print(f"  原始 {len(raw)} 行（含缺失/重复/异常）")
    clean_rows = cl.clean(raw, numeric_cols=["temp_c", "vibration_mm_s", "power_kw", "pressure_bar"],
                          fill_missing="drop", outlier_method="iqr")
    rpt = cl.report
    print(f"  去重 {rpt['dropped_dup']} 行 | 删缺失 {rpt['missing_by_col'].get('temp_c', 0)} 行 | 删异常 {rpt['dropped_outlier']} 行")
    print(f"  清洗后 {len(clean_rows)} 行")

    # 2. 数据分析（温度列）
    print("\n[2/4] 数据分析（温度 ℃）...")
    temps = [float(r["temp_c"]) for r in clean_rows if r.get("temp_c")]
    desc = stats_mod.describe(temps)
    print(f"  均值 {desc['mean']} | 中位数 {desc['median']} | 标准差 {desc['std']}")
    print(f"  min {desc['min']} | max {desc['max']}")

    # 3. 异常检测 + SPC 控制图
    print("\n[3/4] 异常检测 + SPC 控制图...")
    anomalies = stats_mod.detect_anomaly(temps, method="zscore")
    cc = stats_mod.control_chart(temps)
    print(f"  异常点(zscore>3σ): {len(anomalies)} 个")
    for a in anomalies[:5]:
        print(f"    点{a['index']}: 值={a['value']} z={a['zscore']}")
    print(f"  控制图: 中心={cc['mean']} UCL={cc['ucl']} LCL={cc['lcl']}")
    if cc.get("out_of_control"):
        print(f"  ⚠️ 失控点: {len(cc['out_of_control'])} 个（超控制限，需现场关注）")
        for o in cc["out_of_control"][:3]:
            print(f"    点{o['index']}: 值={o['value']} 超{o['violation']}")
    else:
        print("  ✅ 过程受控")

    # 4. 趋势分析
    print("\n[4/4] 趋势 + 相关性...")
    tr = stats_mod.trend(temps)
    print(f"  温度趋势: {tr['direction']}（斜率 {tr['slope']}）")
    vib = [float(r["vibration_mm_s"]) for r in clean_rows if r.get("vibration_mm_s")]
    corr = stats_mod.correlation(temps, vib)
    print(f"  温度↔振动相关: {corr}")

    print("\n== 完成：工厂现场数据处理闭环 ==")
    print("说明：清洗喂干净数据 → 分析得状态 → 异常检测预警 → 为本体建模做基础。")


if __name__ == "__main__":
    main()
