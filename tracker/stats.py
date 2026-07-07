# -*- coding: utf-8 -*-
"""收益、偏离和跟踪误差计算。"""

import numpy as np


def endpoint(df, value_col: str, target_date):
    """取不晚于目标日期的最后一条记录。"""
    ordered = df.sort_values("date")
    subset = ordered[ordered.date <= target_date]
    if len(subset) == 0:
        return None, None
    row = subset.iloc[-1]
    return row["date"], row[value_col]


def cumulative_return(df, value_col: str, start_date, end_date) -> float:
    """统计区间累计涨幅，端点使用“不晚于目标日期”的最近值。"""
    _start_date, start_value = endpoint(df, value_col, start_date)
    _end_date, end_value = endpoint(df, value_col, end_date)
    if start_value is None or end_value is None:
        return float("nan")
    return (end_value / start_value - 1) * 100


def monthly_returns(df, value_col: str, start_date, end_date):
    """计算月末收益率。

    使用月度而非日度，是为了降低跨市场交易日、节假日和汇率估值时点错位带来的噪音。
    """
    monthly = df[(df.date >= start_date) & (df.date <= end_date)].set_index("date")[value_col].resample("ME").last()
    return monthly.dropna().pct_change()


def calendar_year_returns(df, value_col: str, years, start_date):
    """分自然年收益。

    首年使用统计区间起点作为基准；后续年份使用上一年最后一个可用净值作为基准。
    """
    ordered = df.sort_values("date")
    out = {}
    for year in years:
        if year == years[0]:
            base_rows = ordered[ordered.date <= start_date][value_col]
            if len(base_rows) == 0:
                continue
            base = base_rows.iloc[-1]
        else:
            prior = ordered[ordered.date.dt.year == year - 1][value_col]
            if len(prior) == 0:
                continue
            base = prior.iloc[-1]

        end_rows = ordered[ordered.date.dt.year == year][value_col]
        if len(end_rows) == 0:
            continue
        out[year] = end_rows.iloc[-1] / base - 1
    return out


def tracking_error(fund_monthly, index_monthly) -> float:
    """年化跟踪误差：月度收益差的标准差乘以 sqrt(12)。"""
    joined = fund_monthly.to_frame("f").join(index_monthly.to_frame("i"), how="inner").dropna()
    return (joined["f"] - joined["i"]).std() * np.sqrt(12) * 100


def dca_avg_premium(market_df, n_days: int = None, price_col: str = "close") -> float:
    """计算定投平均溢价：近N天每天买入相同股数，实际成本相对净值的溢价。

    公式：sum(price) / sum(nav) - 1
    n_days=None 时取全部历史数据。
    price_col: 使用的价格列，'close' 或 'vwap'
    """
    if market_df is None or len(market_df) == 0:
        return float("nan")

    df = market_df.sort_values("date").tail(n_days) if n_days else market_df
    if len(df) == 0:
        return float("nan")

    total_cost = df[price_col].sum()
    total_nav = df["nav"].sum()

    if total_nav == 0:
        return float("nan")

    return (total_cost / total_nav - 1) * 100


def dca_premium_std(market_df, n_days: int = None, price_col: str = "close") -> float:
    """计算定投期内每日溢价率的标准差，衡量溢价波动性。

    price_col: 使用的价格列，'close' 或 'vwap'
    """
    if market_df is None or len(market_df) == 0:
        return float("nan")
    df = market_df.sort_values("date").tail(n_days) if n_days else market_df
    valid = df[df["nav"] > 0]
    if len(valid) == 0:
        return float("nan")
    return ((valid[price_col] / valid["nav"] - 1) * 100).std()
