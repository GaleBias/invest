# -*- coding: utf-8 -*-
"""数据下载与落盘。

下载模块只负责把外部数据源写成统一 xlsx 格式，不负责计算收益或生成报告。
A 股基金是主比较对象，任一下载失败即停止，避免后续报告混用旧数据。
香港安硕是参考项，下载失败时只打印错误，不影响主报告。
"""

import io
import ssl
import urllib.request

import pandas as pd

from tracker.config import (
    DATA_COLUMNS,
    DEFAULT_USE_TOTAL_RETURN,
    FUNDS,
    FX_FILE,
    HKFX_FILE,
    INDEX_FILE_NDX,
    INDEX_FILE_XNDX,
    REF_FUNDS,
    USER_AGENT,
    ensure_data_dir,
    fund_file,
)


def _get(url: str, timeout: int = 30, retries: int = 2) -> bytes:
    """带简单重试的 HTTP GET，使用分块读取避免大文件 IncompleteRead。"""
    import time
    req = urllib.request.Request(url, headers=USER_AGENT)
    # 创建宽松的 SSL context，解决 Yahoo Finance 等站点的握手兼容问题
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            chunks = []
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                wait = (attempt + 1) * 3  # 递增等待：3s, 6s, 9s...
                print(f"  [重试 {attempt + 1}/{retries}] {type(exc).__name__}: {exc}")
                print(f"    等待 {wait}s 后重试...")
                time.sleep(wait)
    raise last_err


def _fetch_etf_market_data(code: str) -> dict:
    """用 akshare 获取场内历史数据，返回 {date_str: {close, vwap, high, low}}。"""
    try:
        import akshare as ak
        prefix = "sh" if code.startswith("51") or code.startswith("16") else "sz"
        symbol = f"{prefix}{code}"
        df = ak.fund_etf_hist_sina(symbol=symbol)
        df["vwap"] = df["amount"] / df["volume"]  # 成交额/成交量 = VWAP
        result = {}
        for _, row in df.iterrows():
            date = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
            result[date] = {
                "close": float(row["close"]),
                "vwap": round(float(row["vwap"]), 4),
                "high": float(row["high"]),
                "low": float(row["low"]),
            }
        return result
    except Exception as exc:
        print(f"  [akshare获取失败] {code}: {exc}")
        return {}


def _fetch_iopv_today() -> dict:
    """获取 ETF 最新 IOPV 估值数据，返回 {code: {iopv, close, high, low}}。

    fund_etf_spot_em 返回的 IOPV 是前一个交易日的净值（尚未同步到历史净值接口）。
    具体对应哪个交易日不在此处推算，由 fetch_fund 结合场内交易数据确定。
    """
    import akshare as ak

    try:
        df = ak.fund_etf_spot_em()
        result = {}
        for _, row in df.iterrows():
            code = str(row["代码"])
            iopv = row.get("IOPV实时估值")
            if pd.isna(iopv) or iopv is None or iopv == 0:
                continue
            result[code] = {
                "iopv": float(iopv),
                "close": float(row["最新价"]) if pd.notna(row.get("最新价")) else "",
                "high": float(row["最高价"]) if pd.notna(row.get("最高价")) else "",
                "low": float(row["最低价"]) if pd.notna(row.get("最低价")) else "",
            }
        return result
    except Exception:
        return {}


def fetch_fund(company: str, code: str, iopv_data: dict = None):
    """通过 akshare 下载东方财富基金净值历史。

    使用 fund_open_fund_info_em 接口分别获取单位净值和累计净值，
    再合并场内交易数据，统一写入 xlsx。

    若历史净值不包含场内交易数据中已有的最新交易日，则用 iopv_data 中的
    IOPV 估值补充该日净值。如果历史净值已经覆盖到场内数据的最新日期，则无需补充。
    """
    import akshare as ak

    ensure_data_dir()

    # 获取单位净值 + 日增长率
    nav_df = ak.fund_open_fund_info_em(symbol=code, indicator='单位净值走势', period='成立来')
    nav_df = nav_df.rename(columns={'净值日期': 'date', '单位净值': 'nav', '日增长率': 'change'})
    nav_df['date'] = pd.to_datetime(nav_df['date']).dt.strftime('%Y-%m-%d')

    # 获取累计净值
    acc_df = ak.fund_open_fund_info_em(symbol=code, indicator='累计净值走势', period='成立来')
    acc_df = acc_df.rename(columns={'净值日期': 'date', '累计净值': 'acc'})
    acc_df['date'] = pd.to_datetime(acc_df['date']).dt.strftime('%Y-%m-%d')

    # 合并
    merged = pd.merge(nav_df, acc_df[['date', 'acc']], on='date', how='left')

    # 获取场内交易数据
    try:
        market_data = _fetch_etf_market_data(code)
    except Exception as exc:
        print(f"  [场内数据获取失败] {code}: {exc}")
        market_data = {}

    # 用 IOPV 补充净值：
    # 场内交易数据（新浪）比历史净值接口更新更快，
    # 如果场内数据中存在净值没有覆盖到的更新日期，用 IOPV 补充那天的净值。
    if iopv_data and code in iopv_data and market_data and len(merged) > 0:
        nav_last_date = merged['date'].max()
        newer_market_dates = sorted([d for d in market_data if d > nav_last_date])

        if newer_market_dates:
            spot = iopv_data[code]
            iopv_val = spot["iopv"]
            # 取场内数据中最新的那个日期作为 IOPV 对应日期
            iopv_date = newer_market_dates[-1]
            last_nav = merged['nav'].iloc[-1]
            last_acc = merged['acc'].iloc[-1]
            if last_nav and last_acc and last_nav > 0:
                est_acc = round(last_acc * (iopv_val / last_nav), 4)
            else:
                est_acc = iopv_val
            change_pct = round((iopv_val / last_nav - 1) * 100, 2) if last_nav and last_nav > 0 else ""
            new_row = pd.DataFrame([{
                'date': iopv_date,
                'nav': iopv_val,
                'change': change_pct,
                'acc': est_acc,
            }])
            merged = pd.concat([merged, new_row], ignore_index=True)
            print(f"    [IOPV补充] {code} {iopv_date}: 单位净值={iopv_val}, 累计净值≈{est_acc}")

    rows = []
    prev_nav = None
    for _, row in merged.iterrows():
        date = row['date']
        nav = row['nav']
        change = row['change']
        acc = row['acc']
        mkt = market_data.get(date, {})
        close = mkt.get("close", "")
        # 溢价基于前一交易日净值：盘中交易者只能看到前一天的净值
        premium = round((close - prev_nav) / prev_nav * 100, 2) if close != "" and prev_nav else ""
        rows.append({
            "基金代码": code,
            "基金名称": company,
            "净值日期": date,
            "单位净值(元)": nav,
            "日涨跌": f"{change}%" if pd.notna(change) and change != "" else "",
            "累计净值(元)": acc if pd.notna(acc) else "",
            "场内收盘(元)": close,
            "场内均价(元)": mkt.get("vwap", ""),
            "场内最高(元)": mkt.get("high", ""),
            "场内最低(元)": mkt.get("low", ""),
            "溢价率(%)": premium,
        })
        prev_nav = nav

    df = pd.DataFrame(rows, columns=DATA_COLUMNS).sort_values("净值日期", ascending=False).reset_index(drop=True)
    out = fund_file(company, code)
    df.to_excel(out, index=False)
    print(f"  [基金] {out:<22} {len(df):>5}行  {df['净值日期'].min()} ~ {df['净值日期'].max()}")


def _nasdaq_index(symbol: str, start_date: str) -> pd.DataFrame:
    """下载 Nasdaq 官方指数历史数据。"""
    end = (pd.Timestamp.today() + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    url = (
        f"https://indexes.nasdaqomx.com/Index/ExportHistory/{symbol}"
        f"?startDate={start_date}T00:00:00.000&endDate={end}T00:00:00.000&timeOfDay=EOD"
    )
    data = _get(url, timeout=90, retries=5)
    xdf = pd.read_excel(io.BytesIO(data), sheet_name="History")
    xdf = xdf[xdf["Index Value"] > 0]
    return pd.DataFrame({
        "净值日期": pd.to_datetime(xdf["Trade Date"]).dt.strftime("%Y-%m-%d"),
        "close": xdf["Index Value"].values,
    })


def fetch_index(use_total_return: bool = DEFAULT_USE_TOTAL_RETURN):
    """按配置下载 NDX 或 XNDX。

    NDX：通过 akshare index_us_stock_sina 获取（新浪财经）。
    XNDX：Nasdaq 官方独有，仍从 indexes.nasdaqomx.com 下载。
    """
    import akshare as ak

    ensure_data_dir()
    if use_total_return:
        df = _nasdaq_index("XNDX", "1999-03-04")
        _write_ref(df, "XNDX", "纳斯达克100指数(全收益,含股息,美元)", INDEX_FILE_XNDX)
    else:
        mdf = ak.index_us_stock_sina(symbol='.NDX')
        df = pd.DataFrame({
            "净值日期": pd.to_datetime(mdf["date"]).dt.strftime("%Y-%m-%d"),
            "close": mdf["close"].values,
        })
        _write_ref(df, "NDX", "纳斯达克100指数(价格指数,美元)", INDEX_FILE_NDX)


def fetch_fx():
    """下载 USDCNY，通过 akshare 中行牌价获取。"""
    import akshare as ak

    ensure_data_dir()
    df = ak.currency_boc_sina(symbol='美元', start_date='20100101', end_date=pd.Timestamp.today().strftime('%Y%m%d'))
    # 中行汇买价单位：100美元 = X人民币，需除100转换为 1美元 = X人民币
    out = pd.DataFrame({
        "净值日期": pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d"),
        "close": pd.to_numeric(df["中行汇买价"], errors="coerce") / 100,
    }).dropna(subset=["close"])
    _write_ref(out, "USDCNY", "美元兑人民币汇率(中行)", FX_FILE)


def fetch_hkfx():
    """下载 HKDCNY，通过 akshare 中行牌价获取。"""
    import akshare as ak

    ensure_data_dir()
    df = ak.currency_boc_sina(symbol='港币', start_date='20100101', end_date=pd.Timestamp.today().strftime('%Y%m%d'))
    # 中行汇买价单位：100港币 = X人民币，需除100转换为 1港币 = X人民币
    out = pd.DataFrame({
        "净值日期": pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d"),
        "close": pd.to_numeric(df["中行汇买价"], errors="coerce") / 100,
    }).dropna(subset=["close"])
    _write_ref(out, "HKDCNY", "港币兑人民币汇率(中行)", HKFX_FILE)


def fetch_ishares(company: str, code_disp: str, etfid: str):
    """下载香港安硕 2834 的港币单位净值（MoneyDJ）和场内交易价格（akshare 新浪港股接口）。

    NAV 来自 MoneyDJ（港币单位净值），场内价格来自 akshare stock_hk_daily，
    两者按日期合并，使安硕也能像 A 股基金一样做溢价分析。
    """
    import akshare as ak

    ensure_data_dir()

    # ---- 1. 从 MoneyDJ 获取 NAV ----
    end = pd.Timestamp.today().strftime("%Y%m%d")
    url = f"https://www.moneydj.com/ETF/X/xdjbcd/Basic0003BCD.xdjbcd?etfid={etfid}&b=20100101&c={end}"
    req = urllib.request.Request(
        url,
        headers={**USER_AGENT, "Referer": f"https://www.moneydj.com/ETF/X/Basic/Basic0003.xdjhtm?etfid={etfid}"},
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    raw = urllib.request.urlopen(req, timeout=30, context=ctx).read().decode("utf-8", "ignore").strip()

    seg = raw.split(" ")
    dates = [pd.to_datetime(x, format="%Y%m%d").strftime("%Y-%m-%d") for x in seg[0].split(",")]
    nav_values = [float(x) for x in seg[1].split(",")]
    nav_dict = dict(zip(dates, nav_values))

    # ---- 2. 从 akshare 获取港股场内交易数据 ----
    market_dict = {}
    try:
        # code_disp 形如 "02834"，直接用于 stock_hk_daily
        mdf = ak.stock_hk_daily(symbol=code_disp, adjust='')
        for _, row in mdf.iterrows():
            date_str = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
            close = float(row["close"])
            high = float(row["high"])
            low = float(row["low"])
            volume = float(row["volume"]) if pd.notna(row.get("volume")) else 0
            amount = float(row["amount"]) if pd.notna(row.get("amount")) else 0
            vwap = round(amount / volume, 4) if volume > 0 else round((high + low + close) / 3, 4)
            market_dict[date_str] = {
                "close": round(close, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "vwap": vwap,
            }
    except Exception as exc:
        print(f"  [港股场内数据获取失败] {code_disp}: {exc}")

    # ---- 3. 合并 NAV + 场内价格 ----
    # 按日期排序，溢价基于前一交易日净值
    sorted_dates = sorted(nav_dict.keys())
    rows = []
    prev_nav = None
    for date in sorted_dates:
        nav = nav_dict[date]
        mkt = market_dict.get(date, {})
        close = mkt.get("close", "")
        premium = round((close - prev_nav) / prev_nav * 100, 2) if close != "" and prev_nav else ""
        rows.append({
            "基金代码": code_disp,
            "基金名称": f"iShares纳斯达克100ETF({etfid},港币)",
            "净值日期": date,
            "单位净值(元)": nav,
            "日涨跌": "",
            "累计净值(元)": nav,
            "场内收盘(元)": close,
            "场内均价(元)": mkt.get("vwap", ""),
            "场内最高(元)": mkt.get("high", ""),
            "场内最低(元)": mkt.get("low", ""),
            "溢价率(%)": premium,
        })
        prev_nav = nav

    df = pd.DataFrame(rows, columns=DATA_COLUMNS).sort_values("净值日期", ascending=False).reset_index(drop=True)
    out = fund_file(company, code_disp)
    df.to_excel(out, index=False)
    print(f"  [境外] {out:<22} {len(df):>5}行  {df['净值日期'].min()} ~ {df['净值日期'].max()}")


def _write_ref(df: pd.DataFrame, code: str, name: str, out: str):
    """把指数和汇率写成与基金净值一致的 xlsx 结构。"""
    df = df.drop_duplicates("净值日期").sort_values("净值日期").reset_index(drop=True)
    df["chg"] = df["close"].pct_change() * 100
    rows = [{
        "基金代码": code,
        "基金名称": name,
        "净值日期": row["净值日期"],
        "单位净值(元)": round(row["close"], 4),
        "日涨跌": "" if pd.isna(row["chg"]) else f"{row['chg']:.2f}%",
        "累计净值(元)": round(row["close"], 4),
        "场内收盘(元)": "",
        "场内均价(元)": "",
        "场内最高(元)": "",
        "场内最低(元)": "",
        "溢价率(%)": "",
    } for _, row in df.iterrows()]

    out_df = pd.DataFrame(rows, columns=DATA_COLUMNS).sort_values("净值日期", ascending=False).reset_index(drop=True)
    out_df.to_excel(out, index=False)
    print(f"  [参考] {out:<22} {len(out_df):>5}行  {out_df['净值日期'].min()} ~ {out_df['净值日期'].max()}")


def fetch_all(use_total_return: bool):
    """执行完整下载流程。"""
    print("== 获取 ETF 实时 IOPV 估值 ==")
    iopv_data = _fetch_iopv_today()
    if iopv_data:
        print(f"  获取到 {len(iopv_data)} 只 ETF 的 IOPV 数据")
    else:
        print("  未获取到 IOPV 数据（非交易时间或接口不可用），跳过补充")

    print("== 下载 A股纳指ETF 净值 ==")
    failed_funds = []
    for company, code, _display in FUNDS:
        try:
            fetch_fund(company, code, iopv_data if iopv_data else None)
        except Exception as exc:
            print(f"  [失败] {company}-{code}: {exc}")
            failed_funds.append(f"{company}-{code}: {exc}")

    if failed_funds:
        print("\n[终止] 以下 A股基金下载失败，为避免使用旧数据生成报告，已停止后续流程：")
        for item in failed_funds:
            print(f"  - {item}")
        raise SystemExit(1)

    print("== 下载 指数 / 汇率 ==")
    fetch_index(use_total_return)
    fetch_fx()
    fetch_hkfx()

    print("== 下载 香港 安硕2834 (MoneyDJ) ==")
    for company, code_disp, etfid in REF_FUNDS:
        try:
            fetch_ishares(company, code_disp, etfid)
        except Exception as exc:
            print(f"  [失败] {company}-{code_disp}: {exc}")
