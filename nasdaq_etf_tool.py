#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纳斯达克100 ETF 跟踪对比工具。

默认流程：
1. 下载 A 股纳指 ETF、纳指100指数、汇率和香港安硕 2834 数据。
2. 把美元和港币资产统一换算为人民币口径。
3. 生成跟踪误差与收益偏离对比报告。
"""

import argparse

from tracker.config import DEFAULT_USE_TOTAL_RETURN
from tracker.download import fetch_all
from tracker.report import build_report


def main():
    parser = argparse.ArgumentParser(description="纳指100基金数据抓取与跟踪误差对比")
    parser.add_argument("--skip-download", action="store_true", help="跳过下载，仅用已有 xlsx 生成报告")
    parser.add_argument("--only-download", action="store_true", help="仅下载数据，不生成报告")
    parser.add_argument(
        "--total-return",
        dest="total_return",
        action="store_true",
        default=None,
        help="使用全收益指数 XNDX（含股息，Nasdaq 官方）",
    )
    parser.add_argument(
        "--no-total-return",
        dest="total_return",
        action="store_false",
        help="使用价格指数 NDX（不含股息，Nasdaq 官方）",
    )
    parser.add_argument(
        "--premium-periods",
        type=str,
        default="30",
        help="溢价对比时间窗口（自然日），逗号分隔，如 30,60,90 （默认：30）",
    )
    parser.add_argument(
        "--nav-periods",
        type=str,
        default="30",
        help="净值近期对比窗口（自然日），可选 30/180/365/730，逗号分隔，如 30,180,365 （默认：30=近30天）",
    )
    args = parser.parse_args()

    use_total_return = DEFAULT_USE_TOTAL_RETURN
    if args.total_return is not None:
        use_total_return = args.total_return

    index_name = "全收益指数 XNDX（Nasdaq 官方）" if use_total_return else "价格指数 NDX（Nasdaq 官方）"
    print(f"[指数口径] {index_name}")

    if not args.skip_download:
        fetch_all(use_total_return)

    if not args.only_download:
        print("\n== 生成对比报告 ==")
        premium_periods = [(f"近{d}天", int(d)) for d in args.premium_periods.split(",") if d.strip().isdigit()]
        nav_periods = [int(d) for d in args.nav_periods.split(",") if d.strip().isdigit()]
        build_report(use_total_return, premium_periods or None, nav_periods or None)


if __name__ == "__main__":
    main()
