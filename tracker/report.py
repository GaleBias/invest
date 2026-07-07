# -*- coding: utf-8 -*-
"""Markdown 报告生成。"""

import numpy as np
import pandas as pd

from tracker.config import FUNDS, REPORT_FILE, fund_file
from tracker.data import load_a_share_funds, load_hkfx, load_index_components, load_market_data, load_reference_funds, load_series
from tracker.stats import calendar_year_returns, cumulative_return, dca_avg_premium, dca_premium_std, endpoint, monthly_returns, tracking_error

_PREMIUM_PERIODS = [("近30天", 30)]

_NAV_RECENT_DEFAULT = [30]


def build_report(use_total_return: bool, premium_periods=None, nav_periods=None):
    ndx, fx, idx = load_index_components(use_total_return)

    series, fund_ranges = load_a_share_funds()
    codes = [code for _company, code, _display in FUNDS]

    ref_loaded = []
    try:
        ref_loaded, ref_ranges = load_reference_funds()
        fund_ranges.update(ref_ranges)
    except Exception as exc:
        print(f"  [安硕折算跳过] {exc}")

    merged = None
    for code in codes:
        merged = series[code] if merged is None else pd.merge(merged, series[code], on="date")
    merged = merged.sort_values("date").reset_index(drop=True)
    start_date, end_date = merged.date.min(), merged.date.max()

    effective_start = max(value[1] for value in fund_ranges.values())
    if effective_start > start_date:
        start_date = effective_start
        merged = merged[merged.date >= start_date].reset_index(drop=True)

    observation_count = len(merged)
    years = sorted(set(merged.date.dt.year))
    latest_start_fund = max(fund_ranges.items(), key=lambda item: item[1][1])

    index_year_returns = {
        year: value * 100
        for year, value in calendar_year_returns(idx, "idx", years, start_date).items()
    }
    index_cum = cumulative_return(idx, "idx", start_date, end_date)
    index_monthly = monthly_returns(idx, "idx", start_date, end_date)

    ndx_start_date, ndx_start_value = endpoint(ndx, "ndx", start_date)
    ndx_end_date, ndx_end_value = endpoint(ndx, "ndx", end_date)
    ndx_cum = cumulative_return(ndx.rename(columns={"ndx": "v"}), "v", start_date, end_date)

    fx_start_date, fx_start_value = endpoint(fx, "fx", start_date)
    fx_end_date, fx_end_value = endpoint(fx, "fx", end_date)
    usd_cum = cumulative_return(fx.rename(columns={"fx": "v"}), "v", start_date, end_date)

    idx_start_date, idx_start_value = endpoint(idx, "idx", start_date)
    idx_end_date, idx_end_value = endpoint(idx, "idx", end_date)

    hk_df = load_hkfx()
    hk_start_date, hk_start_value = endpoint(hk_df, "v", start_date)
    hk_end_date, hk_end_value = endpoint(hk_df, "v", end_date)
    hk_cum = cumulative_return(hk_df, "v", start_date, end_date)

    all_funds = [
        (display, code, load_series(fund_file(company, code), "累计净值(元)"))
        for company, code, display in FUNDS
    ]
    for company, code_disp, ef_df in ref_loaded:
        all_funds.append((company, code_disp, ef_df))

    rows = []
    for display, code, df in all_funds:
        fund_monthly = monthly_returns(df, "v", start_date, end_date)
        te = tracking_error(fund_monthly, index_monthly)
        year_ret = {
            year: calendar_year_returns(df, "v", years, start_date).get(year, np.nan) * 100
            for year in years
        }
        year_dev = {year: year_ret[year] - index_year_returns.get(year, 0) for year in years}
        rows.append({
            "name": display,
            "code": code,
            "te": te,
            "cum": cumulative_return(df, "v", start_date, end_date),
            "ret": year_ret,
            "dev": year_dev,
        })
    rows.sort(key=lambda item: -item["cum"])

    if use_total_return:
        idx_label = "XNDX"
        idx_source = "Nasdaq官方（全收益指数，含股息，美元）"
        idx_note = "XNDX 为全收益指数，含股息再投资，数据来自 Nasdaq 官方（indexes.nasdaqomx.com）。"
    else:
        idx_label = "NDX"
        idx_source = "Nasdaq官方（价格指数，不含股息，美元）"
        idx_note = "NDX 为价格指数，不含股息，与各基金合同声明的跟踪标的一致，数据来自 Nasdaq 官方。"

    lines = ["# 纳斯达克100指数基金 跟踪误差对比报告\n"]
    _append_overview(
        lines, idx_label, idx_source, start_date, end_date, observation_count, latest_start_fund,
        fund_ranges, ndx_start_date, ndx_start_value, ndx_end_date, ndx_end_value, ndx_cum,
        idx_start_value, idx_end_value, index_cum, fx_start_date, fx_start_value, fx_end_date,
        fx_end_value, usd_cum, hk_start_date, hk_start_value, hk_end_date, hk_end_value, hk_cum,
    )
    period_info = _append_nav_section(lines, years, idx_label, index_year_returns, index_cum, rows, all_funds, idx, end_date, nav_periods)
    _append_premium_section(lines, premium_periods, end_date)
    # _append_scoring(lines, rows, all_funds, period_info, index_cum, end_date)
    _append_method(lines, idx_label, idx_note)

    with open(REPORT_FILE, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
    print(f"\n报告已生成：{REPORT_FILE}")
    print("\n".join(lines[:30 + len(rows) + 4]))


def _append_overview(
    lines, idx_label, idx_source, start_date, end_date, observation_count, latest_start_fund,
    fund_ranges, ndx_start_date, ndx_start_value, ndx_end_date, ndx_end_value, ndx_cum,
    idx_start_value, idx_end_value, index_cum, fx_start_date, fx_start_value, fx_end_date,
    fx_end_value, usd_cum, hk_start_date, hk_start_value, hk_end_date, hk_end_value, hk_cum,
):
    lines.append("## 一、数据概览\n")
    lines.append("**数据来源**\n")
    lines.append("| 数据 | 来源 | 说明 |")
    lines.append("|---|---|---|")
    lines.append("| A股ETF净值 | 东方财富（akshare） | fund_open_fund_info_em，含单位净值和累计净值 |")
    lines.append("| A股ETF场内价格 | 新浪财经（akshare） | fund_etf_hist_sina，含收盘价、最高价、最低价、成交额 |")
    lines.append("| A股ETF IOPV | 东方财富（akshare） | fund_etf_spot_em，用于补充净值接口尚未更新的交易日 |")
    lines.append("| 安硕2834净值 | MoneyDJ | 港币单位净值 |")
    lines.append("| 安硕2834场内价格 | 新浪财经（akshare） | stock_hk_daily，港股日线行情 |")
    lines.append(f"| 纳指100指数 {idx_label} | Nasdaq官方 | {idx_source} |")
    lines.append("| USDCNY汇率 | Yahoo Finance | 日频收盘汇率 |")
    lines.append("| HKDCNY汇率 | Yahoo Finance | 日频收盘汇率 |")
    lines.append("")
    lines.append(f"**统计区间：{start_date.date()} ~ {end_date.date()}**（各基金共同交易日，共 {observation_count} 个）\n")
    lines.append(
        f"由 **{latest_start_fund[0]}**（代码 {latest_start_fund[1][0]}，"
        f"数据起始于 {latest_start_fund[1][1].date()}）决定区间起点。\n"
    )
    lines.append("| 基金 | 代码 | 数据起始 | 数据截止 |")
    lines.append("|---|---|---|---|")
    for display, (code, data_start, data_end) in sorted(fund_ranges.items(), key=lambda item: item[1][1]):
        lines.append(f"| {display} | {code} | {data_start.date()} | {data_end.date()} |")
    lines.append("")
    lines.append("**统计区间内指数与汇率变动**\n")
    lines.append(f"| | 起点（{ndx_start_date.date()}） | 终点（{ndx_end_date.date()}） | 累计变动 |")
    lines.append("|---|---|---|---|")
    lines.append(f"| 纳指100(美元) | {ndx_start_value:.2f} | {ndx_end_value:.2f} | **{ndx_cum:+.2f}%** |")
    lines.append(f"| 纳指100(人民币) | {idx_start_value:.2f} | {idx_end_value:.2f} | **{index_cum:+.2f}%** |")
    lines.append(f"| USDCNY 汇率 | {fx_start_value:.4f} | {fx_end_value:.4f} | {usd_cum:+.2f}% |")
    lines.append(f"| HKDCNY 汇率 | {hk_start_value:.4f} | {hk_end_value:.4f} | {hk_cum:+.2f}% |")
    lines.append("")
    lines.append(f"> 汇率变动说明：")
    lines.append(f"> - 正值 = 外币升值（人民币贬值），负值 = 外币贬值（人民币升值）。")
    lines.append(f"> - 人民币涨幅 ≈ 美元涨幅 × (1 + USDCNY变动)，即 {ndx_cum:+.2f}% × (1 {usd_cum / 100:+.4f}) ≈ {index_cum:+.2f}%。")
    lines.append("")
    lines.append("---\n")


def _append_nav_section(lines, years, idx_label, index_year_returns, index_cum, rows, all_funds, idx, end_date, nav_periods=None):
    """二、净值对比结果：总表 + 近半年/近1年/近2年。"""
    # 总表
    ret_headers = [f"{year}{'至今' if year == years[-1] else ''}涨幅" for year in years]
    dev_headers = [f"{year}{'至今' if year == years[-1] else ''}偏离" for year in years]
    year_header = " | ".join(ret_headers + ["累计涨幅"] + dev_headers + ["累计偏离"])

    lines.append("## 二、净值对比结果\n")
    lines.append("比较各基金与纳指100人民币指数的收益差距，衡量跟踪质量。\n")
    lines.append(f"### 2.1 年度总表（按累计涨幅排名，截止 {end_date.date()}）\n")
    lines.append("按自然年统计各基金涨幅，与指数对比偏离程度。\n")
    lines.append(f"| 排名 | 基金 | 代码 | {year_header} | 年化跟踪误差 |")
    lines.append("|---|---|---|" + "---|" * (len(years) * 2 + 3))

    index_ret = [f"{index_year_returns.get(year, float('nan')):+.2f}%" for year in years]
    index_dev = ["基准"] * len(years)
    index_row = " | ".join(index_ret + [f"**{index_cum:+.2f}%**"] + index_dev + ["基准"])
    lines.append(f"| — | **纳指100指数(人民币)** | {idx_label} | {index_row} | 基准 |")

    for rank, row in enumerate(rows, 1):
        ret_parts = [f"{row['ret'][year]:+.2f}%" for year in years]
        dev_parts = [f"{row['dev'][year]:+.2f}" if not np.isnan(row["dev"][year]) else "—" for year in years]
        cells = " | ".join(ret_parts + [f"{row['cum']:+.2f}%"] + dev_parts + [f"{row['cum'] - index_cum:+.2f}"])
        lines.append(f"| {rank} | {row['name']} | {row['code']} | {cells} | {row['te']:.2f}% |")

    lines += [
        "",
        "> 说明：",
        "> - **涨幅**：该自然年内的收益率（人民币口径）。**偏离**：基金当年涨幅 − 指数当年涨幅（百分点，正=跑赢，负=跑输）。",
        "> - **累计涨幅 / 累计偏离**：统计区间内的累计收益、及相对指数的累计偏离（百分点）。",
        "> - **年化跟踪误差**：月度收益差的年化标准差，越小=跟得越紧越稳。",
        "",
    ]

    # 近期分段表
    lines.append(f"### 2.2 近期净值涨幅（自定义窗口）\n")
    lines.append("按指定的自然日天数划分窗口，对比各基金近期表现与指数的偏离。\n")

    if nav_periods is None:
        nav_periods = _NAV_RECENT_DEFAULT
    recent_periods = [
        (f"近{d}天", pd.Timestamp(end_date) - pd.Timedelta(days=d))
        for d in nav_periods
    ]


    period_info = []
    for period_name, period_start in recent_periods:
        # 用第一只 A 股基金确定实际起始日（A 股交易日历），与溢价表对齐
        actual_period_start = None
        for _display, _code, df in all_funds:
            _d, _v = endpoint(df, "v", period_start)
            if _d is not None:
                actual_period_start = _d
                break
        if actual_period_start is None:
            actual_period_start = period_start

        idx_start_date, idx_start_value = endpoint(idx, "idx", actual_period_start)
        idx_end_date, idx_end_value = endpoint(idx, "idx", end_date)
        if idx_start_value is None or idx_end_value is None:
            period_info.append((period_name, None, None, None, None, float("nan")))
        else:
            idx_ret = (idx_end_value / idx_start_value - 1) * 100
            period_info.append((period_name, actual_period_start, idx_end_date, idx_start_value, idx_end_value, idx_ret))

    for period_name, start_date, _actual_end, idx_start_value, idx_end_value, idx_ret in period_info:
        if start_date is None:
            continue
        lines.append(f"#### {period_name}（{start_date.date()} ~ {end_date.date()}）\n")
        lines.append("| 排名 | 基金 | 代码 | 起始净值 | 终止净值 | 涨幅(人民币) | 偏离 |")
        lines.append("|---|---|---|---|---|---|---|")
        lines.append(
            f"| — | **纳指100指数(人民币)** | {idx_label} | "
            f"{idx_start_value:,.2f} | {idx_end_value:,.2f} | **{idx_ret:+.2f}%** | 基准 |"
        )

        fund_rows = []
        for display, code, df in all_funds:
            _fund_start_date, fund_start_value = endpoint(df, "v", start_date)
            _fund_end_date, fund_end_value = endpoint(df, "v", end_date)
            if fund_start_value is None or fund_end_value is None:
                continue
            fund_ret = (fund_end_value / fund_start_value - 1) * 100
            nav_col = "nav" if "nav" in df.columns else "v"
            _nav_start_date, nav_start = endpoint(df, nav_col, start_date)
            _nav_end_date, nav_end = endpoint(df, nav_col, end_date)
            fund_rows.append({"name": display, "code": code, "nav_s": nav_start, "nav_e": nav_end, "ret": fund_ret})

        fund_rows.sort(key=lambda item: item["ret"], reverse=True)
        for rank, row in enumerate(fund_rows, 1):
            dev = row["ret"] - idx_ret
            lines.append(
                f"| {rank} | {row['name']} | {row['code']} | {row['nav_s']:.4f} | "
                f"{row['nav_e']:.4f} | {row['ret']:+.2f}% | {dev:+.2f} |"
            )
        lines.append("")

    lines += [
        "> 说明：",
        "> - 起始净值中，安硕为港币单位净值，其余基金为人民币累计净值。",
        "> - 涨幅统一为人民币口径。",
        "> - 偏离 = 基金涨幅 − 指数涨幅（百分点）。",
        "",
        "---\n",
    ]
    return period_info


def _append_premium_section(lines, periods=None, end_date=None):
    """三、溢价对比结果：每个时间窗口展示溢价成本、加减仓阈值、涨幅与定投收益。

    Args:
        lines: 输出行列表
        periods: 自定义周期列表，格式 [(label, days), ...]，默认使用 _PREMIUM_PERIODS
        end_date: 统一截止日期，对齐各基金净值更新时间差
    """
    if periods is None:
        periods = _PREMIUM_PERIODS

    fund_data = []
    for company, code, display in FUNDS:
        try:
            mdf = load_market_data(fund_file(company, code))
        except Exception:
            continue
        if mdf is None or len(mdf) == 0:
            continue
        fund_data.append({"name": display, "code": code, "mdf": mdf})

    if not fund_data:
        return

    lines.append("## 三、溢价对比结果\n")
    lines.append("比较各基金的场内交易溢价水平，衡量定投的实际买入成本。按指定的自然日天数划分窗口，模拟每日定投。\n")

    for label, n in periods:
        rows = []
        # 记录实际窗口起止日期
        if n:
            cutoff = (end_date if end_date else pd.Timestamp.now()) - pd.Timedelta(days=n)
        else:
            cutoff = None
        actual_start = None
        actual_end = None

        for item in fund_data:
            mdf = item["mdf"]
            # 统一截止日期，避免不同基金净值更新时间差
            aligned = mdf[mdf["date"] <= end_date] if end_date else mdf
            if n:
                # 包含 cutoff 当天及之前最近一条，与净值对比表的 endpoint 逻辑对齐
                before_cutoff = aligned[aligned["date"] <= cutoff]
                if len(before_cutoff) > 0:
                    actual_cutoff = before_cutoff["date"].iloc[-1]
                    window = aligned[aligned["date"] >= actual_cutoff]
                else:
                    window = aligned[aligned["date"] >= cutoff]
            else:
                window = aligned
            if len(window) < 2:
                continue

            # 更新实际起止日期
            w_start = window["date"].iloc[0]
            w_end = window["date"].iloc[-1]
            if actual_start is None or w_start < actual_start:
                actual_start = w_start
            if actual_end is None or w_end > actual_end:
                actual_end = w_end

            # 计算窗口期净值涨幅
            nav_return = (window["nav"].iloc[-1] / window["nav"].iloc[0] - 1) * 100

            # 计算窗口期场内涨幅（收盘价首尾对比）
            close_window = window.dropna(subset=["close"])
            if len(close_window) >= 2:
                close_return = (close_window["close"].iloc[-1] / close_window["close"].iloc[0] - 1) * 100
            else:
                close_return = float("nan")

            # 计算收盘价溢价
            close_window = window.dropna(subset=["close"])
            if len(close_window) > 0:
                close_avg = dca_avg_premium(close_window, None, "close")
                close_std = dca_premium_std(close_window, None, "close")
                # DCA买入收益：按收盘价定投，相比最终收盘价的涨幅
                avg_cost_close = close_window["close"].mean()
                final_close = close_window["close"].iloc[-1]
                close_dca_ret = (final_close / avg_cost_close - 1) * 100 if avg_cost_close > 0 else float("nan")
            else:
                close_avg = close_std = close_dca_ret = float("nan")

            # 计算均价溢价
            vwap_window = window.dropna(subset=["vwap"])
            if len(vwap_window) > 0:
                vwap_avg = dca_avg_premium(vwap_window, None, "vwap")
                vwap_std = dca_premium_std(vwap_window, None, "vwap")
                # DCA买入收益：按均价定投，相比最终收盘价的涨幅
                avg_cost_vwap = vwap_window["vwap"].mean()
                final_close_vwap = vwap_window["close"].iloc[-1] if "close" in vwap_window.columns and len(vwap_window.dropna(subset=["close"])) > 0 else float("nan")
                vwap_dca_ret = (final_close_vwap / avg_cost_vwap - 1) * 100 if avg_cost_vwap > 0 and not np.isnan(final_close_vwap) else float("nan")
            else:
                vwap_avg = vwap_std = vwap_dca_ret = float("nan")

            # 计算净值买入收益：按净值定投，相比最终净值的涨幅
            nav_valid = window.dropna(subset=["nav"])
            if len(nav_valid) > 0:
                avg_cost_nav = nav_valid["nav"].mean()
                final_nav = nav_valid["nav"].iloc[-1]
                nav_dca_ret = (final_nav / avg_cost_nav - 1) * 100 if avg_cost_nav > 0 else float("nan")
            else:
                nav_dca_ret = float("nan")

            # 计算加仓/减仓阈值：基于每天 high/low 计算日内溢价区间
            # 每天：low_prem = low/nav - 1, high_prem = high/nav - 1
            # 每天25% = low_prem + (high_prem - low_prem) × 25%
            # 每天75% = low_prem + (high_prem - low_prem) × 75%
            # 最终阈值 = 窗口内所有天的25%/75%的均值
            hl_valid = window[(window["nav"] > 0) & window["high"].notna() & window["low"].notna()]
            if len(hl_valid) > 0:
                daily_low_prem = (hl_valid["low"] / hl_valid["nav"] - 1) * 100
                daily_high_prem = (hl_valid["high"] / hl_valid["nav"] - 1) * 100
                daily_range = daily_high_prem - daily_low_prem
                daily_q25 = daily_low_prem + daily_range * 0.25
                daily_q75 = daily_low_prem + daily_range * 0.75
                premium_threshold = daily_q25.mean()
                premium_reduce = daily_q75.mean()
            else:
                premium_threshold = float("nan")
                premium_reduce = float("nan")

            rows.append({
                "name": item["name"],
                "code": item["code"],
                "nav_ret": nav_return,
                "close_ret": close_return,
                "close_avg": close_avg,
                "close_std": close_std,
                "vwap_avg": vwap_avg,
                "vwap_std": vwap_std,
                "close_dca_ret": close_dca_ret,
                "vwap_dca_ret": vwap_dca_ret,
                "nav_dca_ret": nav_dca_ret,
                "premium_threshold": premium_threshold,
                "premium_reduce": premium_reduce,
            })

        if not rows:
            continue

        # 综合得分（满分100）：排名加权
        # 收盘定投收益50%（越高越好）+ 收盘溢价30%（越低越好）+ 溢价σ20%（越低越好）
        nf = len(rows)
        denom = max(nf - 1, 1)

        for i, r in enumerate(sorted(rows, key=lambda x: x["close_dca_ret"] if not np.isnan(x["close_dca_ret"]) else float("-inf"), reverse=True)):
            r["_ret_rank"] = i
        for i, r in enumerate(sorted(rows, key=lambda x: x["close_avg"] if not np.isnan(x["close_avg"]) else float("inf"))):
            r["_prem_rank"] = i
        for i, r in enumerate(sorted(rows, key=lambda x: x["close_std"] if not np.isnan(x["close_std"]) else float("inf"))):
            r["_std_rank"] = i

        for r in rows:
            ret_score  = (denom - r["_ret_rank"])  / denom * 100
            prem_score = (denom - r["_prem_rank"]) / denom * 100
            std_score  = (denom - r["_std_rank"])  / denom * 100
            r["score"] = ret_score * 0.50 + prem_score * 0.30 + std_score * 0.20

        rows.sort(key=lambda r: r["score"], reverse=True)

        date_range = ""
        if actual_start and actual_end:
            date_range = f"（{actual_start.date()} ~ {actual_end.date()}）"
        lines.append(f"#### {label}{date_range}\n")
        lines.append("| 排名 | 基金 | 代码 | 收盘溢价(±σ) | 均价溢价(±σ) | 加仓阈值 | 减仓阈值 | 净值涨幅 | 场内涨幅 | 净值定投收益 | 收盘定投收益 | 均价定投收益 | 综合得分 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")

        for rank, row in enumerate(rows, 1):
            close_ret_s = f"{row['close_dca_ret']:+.2f}%" if not np.isnan(row['close_dca_ret']) else "—"
            vwap_ret_s  = f"{row['vwap_dca_ret']:+.2f}%"  if not np.isnan(row['vwap_dca_ret'])  else "—"
            nav_dca_s   = f"{row['nav_dca_ret']:+.2f}%"   if not np.isnan(row['nav_dca_ret'])   else "—"
            nav_s       = f"{row['nav_ret']:+.2f}%"        if not np.isnan(row['nav_ret'])        else "—"
            close_r_s   = f"{row['close_ret']:+.2f}%"     if not np.isnan(row['close_ret'])     else "—"
            premium_med_s = f"{row['premium_threshold']:+.2f}%" if not np.isnan(row['premium_threshold']) else "—"
            premium_red_s = f"{row['premium_reduce']:+.2f}%" if not np.isnan(row['premium_reduce']) else "—"
            score_s     = f"**{row['score']:.0f}**"

            if not np.isnan(row['close_avg']):
                close_s = f"{row['close_avg']:+.2f}%"
                if not np.isnan(row['close_std']):
                    close_s += f"(±{row['close_std']:.2f}%)"
            else:
                close_s = "—"

            if not np.isnan(row['vwap_avg']):
                vwap_s = f"{row['vwap_avg']:+.2f}%"
                if not np.isnan(row['vwap_std']):
                    vwap_s += f"(±{row['vwap_std']:.2f}%)"
            else:
                vwap_s = "—"

            lines.append(f"| {rank} | {row['name']} | {row['code']} | {close_s} | {vwap_s} | {premium_med_s} | {premium_red_s} | {nav_s} | {close_r_s} | {nav_dca_s} | {close_ret_s} | {vwap_ret_s} | {score_s} |")

        lines += [
            "",
        ]

    lines += [
        "> **列说明**",
        ">",
        "> | 列名 | 计算方式 |",
        "> |---|---|",
        "> | 收盘溢价(±σ) | Σ(每天收盘价) / Σ(每天净值) - 1，括号内σ为每日溢价率的标准差 |",
        "> | 均价溢价(±σ) | Σ(每天VWAP) / Σ(每天净值) - 1，按成交均价定投的累计溢价成本 |",
        "> | 加仓阈值 | 每天：最低价/净值-1 + (最高价/净值-1 - 最低价/净值-1)×25%，取窗口内均值。溢价低于此值时加大定投 |",
        "> | 减仓阈值 | 同理取日内75%分位的均值。溢价高于此值时减少定投 |",
        "> | 净值涨幅 | 末日净值 / 首日净值 - 1 |",
        "> | 场内涨幅 | 末日收盘价 / 首日收盘价 - 1 |",
        "> | 净值定投收益 | 末日净值 / 平均净值 - 1（无溢价的理想参考） |",
        "> | 收盘定投收益 | 末日收盘价 / 平均收盘价 - 1（实际场内定投效果） |",
        "> | 均价定投收益 | 末日收盘价 / 平均VWAP - 1（按均价买入的效果） |",
        "> | 综合得分 | 满分100，组内排名加权：收盘定投收益50% + 收盘溢价30% + 溢价σ20% |",
        ">",
        "> **综合得分设计思路**：场内定投最终看实际到手收益（50%权重），同等收益下优先选溢价低的基金（30%权重），溢价波动小意味着买入时机不敏感、更适合纪律性定投（20%权重）。三个维度相互独立，避免重复计算。",
        "",
        "---\n",
    ]


def _append_scoring(lines, rows, all_funds, period_info, index_cum, end_date):
    """四、综合建议排序：结合净值跟踪质量与场内溢价成本（仅A股ETF）。"""
    lines.append("## 四、综合建议排序\n")

    # 只保留A股ETF（排除安硕等境外基金）
    a_share_codes = {code for _company, code, _display in FUNDS}
    rows = [r for r in rows if r["code"] in a_share_codes]
    all_funds = [(name, code, df) for name, code, df in all_funds if code in a_share_codes]

    fund_period_devs = {}
    for period_name, start_date, _actual_end, idx_start_value, idx_end_value, idx_ret in period_info:
        if start_date is None:
            continue
        for _display, code, df in all_funds:
            _fund_start_date, fund_start_value = endpoint(df, "v", start_date)
            _fund_end_date, fund_end_value = endpoint(df, "v", end_date)
            if fund_start_value is None or fund_end_value is None:
                continue
            fund_ret = (fund_end_value / fund_start_value - 1) * 100
            fund_period_devs.setdefault(code, {})[period_name] = fund_ret - idx_ret

    fund_premium_data = {}
    for company, code, display in FUNDS:
        try:
            mdf = load_market_data(fund_file(company, code))
            valid_mdf = mdf.dropna(subset=["close"])
            if len(valid_mdf) == 0:
                continue
            fund_premium_data[code] = {
                "avg": dca_avg_premium(valid_mdf, 365, "close"),
                "std": dca_premium_std(valid_mdf, 365, "close"),
            }
        except Exception:
            continue

    # 权重：净值偏离45%（按实际可用周期按比例分配）+ 跟踪误差15% + 近1年收盘溢价均值25% + 溢价稳定性15%
    _nav_props = {"近半年": 3, "近1年": 4, "近2年": 2}
    available_nav_periods = [p for p, sd, *_ in period_info if sd is not None]
    present_props = {p: _nav_props[p] for p in available_nav_periods if p in _nav_props}
    total_prop = sum(present_props.values()) or 1
    nav_weights = {p: 0.45 * v / total_prop for p, v in present_props.items()}
    te_weight = 0.15
    premium_avg_weight = 0.25
    premium_std_weight = 0.15

    n_funds = len(rows)
    scoring = []
    for row in rows:
        period_devs = fund_period_devs.get(row["code"], {})
        prem = fund_premium_data.get(row["code"], {})
        weighted_nav = sum(
            period_devs.get(p, 0) * w for p, w in nav_weights.items()
        )
        scoring.append({
            "name": row["name"],
            "code": row["code"],
            "te": row["te"],
            "pdevs": period_devs,
            "weighted_nav": weighted_nav,
            "premium_avg": prem.get("avg", float("nan")),
            "premium_std": prem.get("std", float("nan")),
        })

    for rank, item in enumerate(sorted(scoring, key=lambda x: -x["weighted_nav"]), 1):
        item["nav_rank"] = rank
    for rank, item in enumerate(sorted(scoring, key=lambda x: x["te"]), 1):
        item["te_rank"] = rank
    for rank, item in enumerate(sorted(scoring, key=lambda x: x["premium_avg"] if not np.isnan(x["premium_avg"]) else float("inf")), 1):
        item["prem_avg_rank"] = rank
    for rank, item in enumerate(sorted(scoring, key=lambda x: x["premium_std"] if not np.isnan(x["premium_std"]) else float("inf")), 1):
        item["prem_std_rank"] = rank

    denom = max(n_funds - 1, 1)
    for item in scoring:
        item["nav_score"] = (n_funds - item["nav_rank"]) / denom * 100
        item["te_score"] = (n_funds - item["te_rank"]) / denom * 100
        item["prem_avg_score"] = (n_funds - item["prem_avg_rank"]) / denom * 100
        item["prem_std_score"] = (n_funds - item["prem_std_rank"]) / denom * 100
        item["score"] = (
            item["nav_score"] * sum(nav_weights.values())
            + item["te_score"] * te_weight
            + item["prem_avg_score"] * premium_avg_weight
            + item["prem_std_score"] * premium_std_weight
        )
    scoring.sort(key=lambda x: -x["score"])

    dev_col_headers = " | ".join(f"{p}偏离" for p in available_nav_periods)
    lines.append(f"| 排名 | 基金 | 代码 | 综合得分 | {dev_col_headers} | 跟踪误差 | 近1年收盘溢价 | 溢价σ |")
    lines.append("|---|---|---|---|" + "---|" * (len(available_nav_periods) + 3))

    for rank, item in enumerate(scoring, 1):
        dev_cells = " | ".join(
            f"{item['pdevs'].get(p, float('nan')):+.2f}" if not np.isnan(item['pdevs'].get(p, float('nan'))) else "—"
            for p in available_nav_periods
        )
        prem_avg_s = f"{item['premium_avg']:+.2f}%" if not np.isnan(item["premium_avg"]) else "—"
        prem_std_s = f"{item['premium_std']:.2f}%" if not np.isnan(item["premium_std"]) else "—"
        lines.append(
            f"| {rank} | {item['name']} | {item['code']} | **{item['score']:.0f}** | "
            f"{dev_cells} | {item['te']:.2f}% | {prem_avg_s} | {prem_std_s} |"
        )

    nav_weight_desc = " + ".join(f"{p}{int(w*100)}%" for p, w in nav_weights.items())
    lines += [
        "",
        "> **综合得分算法**（满分100）：",
        f"> - 净值偏离（{int(sum(nav_weights.values())*100)}%）：{nav_weight_desc}，基金涨幅 − 指数涨幅（百分点）。",
        f"> - 跟踪误差（{int(te_weight*100)}%）：月度偏离的年化标准差，越小越稳。",
        f"> - 近1年收盘溢价均值（{int(premium_avg_weight*100)}%）：定投收盘价相对净值的累计溢价，越低场内买入成本越小。",
        f"> - 近1年溢价稳定性σ（{int(premium_std_weight*100)}%）：日溢价率标准差，越小每天波动越平稳。",
        "> - 此评分综合了**净值跟踪质量**与**场内交易成本**，适合定投A股场内ETF的投资者参考。",
        "",
    ]


def _append_method(lines, idx_label, idx_note):
    """四、方法与口径说明。"""
    lines.append("---\n")
    lines.append("## 四、方法与口径说明\n")
    lines += [
        "| 类别 | 公式 / 说明 |",
        "|---|---|",
        f"| **人民币折算** | 纳指100人民币指数 = {idx_label}(美元) × USDCNY汇率，逐日合成 |",
        "| | 安硕人民币净值 = 港币净值 × HKDCNY汇率 |",
        "| | 汇率缺失日使用前一交易日汇率前向填充（left join + ffill） |",
        "| **统计区间** | 取所有基金数据的交集：从最晚上市的基金开始，到所有基金共同最新的日期结束 |",
        "| **近期窗口** | 例：「近30天」= 从今天往前数30个自然日，找到那天或之前最近的一个交易日，作为窗口起点 |",
        "| | 窗口终点 = 所有基金最新的共同交易日 |",
        "| | 涨幅 = 终点净值 / 起点净值 − 1 |",
        "| **「之前最近的交易日」** | 如果往前数30天落在周末或节假日（没有数据），就再往前顺延到最近一个有数据的交易日 |",
        "| | 例：30天前是周六 → 用周五的数据；30天前是国庆假期 → 用假期前最后一个交易日 |",
        "| | 所有涨幅计算（累计、年度、分段、溢价窗口）都用这个规则确定起止点 |",
        "| **IOPV补充** | 净值接口有时比场内行情慢一天更新 |",
        "| | 如果场内已经有了新一天的交易数据，但净值接口还没更新，就用 IOPV（盘中参考净值）补上这一天 |",
        "| | 补充的日期 = 场内数据中比净值最新日期更晚的那个交易日（直接看数据，不猜日历） |",
        "| | 补充的累计净值 = 前一天累计净值 × (当天IOPV / 前一天单位净值) |",
        "| | 如果净值已经更新到最新，或者查不到IOPV（非交易时间），就不补充 |",
        "| **跟踪误差** | std(基金月收益 − 指数月收益) × √12（月度口径，消除汇率时点噪音） |",
        "| **日溢价率** | (场内价格 / 单位净值 − 1) × 100% |",
        "| **定投累计溢价** | Σ(每天价格) / Σ(每天净值) − 1（模拟每日买入相同股数） |",
        "| **溢价σ** | 窗口内每日溢价率的标准差 |",
        "| **均价 VWAP** | 成交额 / 成交量，反映全天加权平均成交价格 |",
        "| **加仓阈值** | 每天：低溢价 + (高溢价 − 低溢价) × 25%，取窗口均值。溢价 < 此值 → 加大定投 |",
        "| **减仓阈值** | 每天：低溢价 + (高溢价 − 低溢价) × 75%，取窗口均值。溢价 > 此值 → 减少定投 |",
        "| **净值定投收益** | 末日净值 / mean(每天净值) − 1（理想无溢价基准） |",
        "| **收盘定投收益** | 末日收盘价 / mean(每天收盘价) − 1（实际场内定投效果） |",
        "| **均价定投收益** | 末日收盘价 / mean(每天VWAP) − 1 |",
        "| **综合得分** | 满分100，排名加权：收盘定投收益50% + 收盘溢价30% + 溢价σ20% |",
        "| | 排名分 = (基金数 − 排名) / (基金数 − 1) × 100 |",
        "| **跨市场日历** | A股、港股、美股交易日不同，所有合并均按日期匹配，缺失日自然留空 |",
        "| | 港股安硕溢价只在NAV和场内数据同时有值的交易日计算 |",
        "",
    ]

