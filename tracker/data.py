# -*- coding: utf-8 -*-
"""本地 xlsx 数据加载。

下载阶段会把基金、指数、汇率都写成统一列名；这里负责把这些文件读成
报告和统计函数使用的标准时间序列：date + value。
"""

import pandas as pd

from tracker.config import FUNDS, FX_FILE, HKFX_FILE, REF_FUNDS, fund_file, index_file


def load_series(path: str, value_col: str) -> pd.DataFrame:
    """读取一个 xlsx 文件，并统一为 date/v 两列。"""
    df = pd.read_excel(path).rename(columns={"净值日期": "date", value_col: "v"})
    df["date"] = pd.to_datetime(df["date"])
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    return df.dropna(subset=["v"]).sort_values("date").reset_index(drop=True)[["date", "v"]]


def load_index_components(use_total_return: bool):
    """加载美元指数、美元汇率，并合成为人民币指数。

    使用 left join + ffill，确保指数有数据但汇率缺失的日期（如节假日错位）
    仍能用最近可用汇率折算，避免丢失指数数据点。
    """
    ndx = load_series(index_file(use_total_return), "单位净值(元)").rename(columns={"v": "ndx"})
    fx = load_series(FX_FILE, "单位净值(元)").rename(columns={"v": "fx"})
    idx = pd.merge(ndx, fx, on="date", how="left")
    idx = idx.sort_values("date").reset_index(drop=True)
    idx["fx"] = idx["fx"].ffill()
    idx = idx.dropna(subset=["fx"])
    idx["idx"] = idx["ndx"] * idx["fx"]
    idx = idx[["date", "idx", "ndx", "fx"]].reset_index(drop=True)
    return ndx, fx, idx


def load_a_share_funds():
    """加载所有 A 股基金累计净值序列。"""
    series = {}
    fund_ranges = {}
    for company, code, display in FUNDS:
        df = load_series(fund_file(company, code), "累计净值(元)").rename(columns={"v": code})
        series[code] = df
        fund_ranges[display] = (code, df["date"].min(), df["date"].max())
    return series, fund_ranges


def load_reference_funds():
    """加载香港参考基金，并折算为人民币累计净值。

    返回值中 nav 为港币净值，v 为人民币口径净值。
    """
    ref_loaded = []
    ref_ranges = {}
    hk = load_series(HKFX_FILE, "单位净值(元)").rename(columns={"v": "hk"})
    for company, code_disp, _etfid in REF_FUNDS:
        ef = load_series(fund_file(company, code_disp), "累计净值(元)").rename(columns={"v": "nav"})
        ef = pd.merge(ef, hk, on="date", how="left").sort_values("date").reset_index(drop=True)
        ef["hk"] = ef["hk"].ffill()
        ef = ef.dropna(subset=["hk"])
        ef["v"] = ef["nav"] * ef["hk"]
        ref_loaded.append((company, code_disp, ef[["date", "nav", "v"]]))
        ref_ranges[company] = (code_disp, ef["date"].min(), ef["date"].max())
    return ref_loaded, ref_ranges


def load_hkfx():
    return load_series(HKFX_FILE, "单位净值(元)").rename(columns={"v": "v"})


def load_market_data(path: str):
    """加载市场交易数据（场内收盘价、均价、最高、最低、净值等），用于溢价分析。"""
    df = pd.read_excel(path)
    df["date"] = pd.to_datetime(df["净值日期"])
    df["nav"] = pd.to_numeric(df["单位净值(元)"], errors="coerce")
    df["close"] = pd.to_numeric(df["场内收盘(元)"], errors="coerce")
    df["vwap"] = pd.to_numeric(df["场内均价(元)"], errors="coerce")
    df["high"] = pd.to_numeric(df.get("场内最高(元)"), errors="coerce") if "场内最高(元)" in df.columns else float("nan")
    df["low"] = pd.to_numeric(df.get("场内最低(元)"), errors="coerce") if "场内最低(元)" in df.columns else float("nan")
    return df[["date", "nav", "close", "vwap", "high", "low"]].dropna(subset=["date", "nav"]).sort_values("date").reset_index(drop=True)
