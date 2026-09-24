# -*- coding: utf-8 -*-
"""纳斯达克100 估值与历史分位计算。

两种口径：
- TTM（滚动市盈率）：EPS 用过去12个月已实现盈利。数据源：worldperatio（基于 QQQ）。
- Forward（前瞻市盈率）：EPS 用分析师预测的未来12个月盈利。数据源：WSJ（晨报口径）。

分位数两种算法：
- exact_percentile：有完整历史 PE 序列时，用真实排名算分位（最准）。
- normal_percentile：只有历史均值 μ 和标准差 σ 时，用正态近似算分位（够用的估计）。

说明：指数级的免费历史 PE 序列很难拿到，这里对 TTM 采用 worldperatio 公布的
各时间窗口 μ/σ 做正态近似分位；一旦攒到真实日度序列，可切换到 exact_percentile。
"""

import math


def derived_eps(index_level: float, pe: float) -> float:
    """由指数点位和市盈率反推 EPS：EPS = 指数 / PE。"""
    if pe is None or pe == 0:
        return float("nan")
    return index_level / pe


def exact_percentile(value: float, series) -> float:
    """真实历史分位：历史上比 value 低的比例（0~100）。

    series 为完整历史 PE 序列。分位越低越便宜。
    """
    data = [x for x in series if x == x]  # 剔除 NaN
    if not data:
        return float("nan")
    below = sum(1 for x in data if x < value)
    return below / len(data) * 100


def normal_percentile(value: float, mu: float, sigma: float) -> float:
    """正态近似分位：已知历史均值 μ 和标准差 σ 时估计 value 所处分位（0~100）。

    使用标准正态 CDF（math.erf 实现，无需三方依赖）。
    """
    if sigma is None or sigma <= 0:
        return float("nan")
    z = (value - mu) / sigma
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return cdf * 100


def sigma_from_range(low: float, high: float) -> float:
    """由 1σ 区间 [μ-σ, μ+σ] 反推 σ = (high - low) / 2。"""
    return (high - low) / 2


def temperature_label(pct: float) -> str:
    """按分位给出估值温度标签。"""
    if pct != pct:  # NaN
        return "数据不足"
    if pct < 20:
        return "便宜（低估）"
    if pct < 40:
        return "偏低"
    if pct < 60:
        return "合理"
    if pct < 80:
        return "偏高"
    return "昂贵（高估）"


# ---- 已知数据快照（可随时更新）----

# 纳指100点位：对应美东 2026-09-09 收盘（晨报数据）
NDX_LEVEL = 29382.45

# TTM 口径：worldperatio 2026-09-10，基于 QQQ 计算的滚动 PE。
# 各时间窗口给出 (μ, 1σ区间low, 1σ区间high)。
TTM_PE = 28.79
TTM_BANDS = {
    "近1年": (32.95, 32.17, 33.72),
    "近5年": (30.43, 27.44, 33.41),
    "近10年": (27.39, 23.38, 31.40),
    "近20年": (22.62, 17.09, 28.15),
}

# Forward 口径：WSJ 晨报，最新周度（2026-09-04）。
# WSJ 未公布现成的历史 μ/σ，这里给出近年经验区间作参考（可后续用真实序列替换）。
FWD_PE = 25.25
FWD_BANDS = {
    # (μ, 1σ low, 1σ high) —— 经验估计，仅供定位，非官方精确统计
    "近5年(经验)": (23.0, 19.5, 26.5),
    "近10年(经验)": (20.5, 16.0, 25.0),
}


def render() -> str:
    lines = []
    lines.append(f"纳指100点位（2026-09-09 收盘）：{NDX_LEVEL:,.2f}\n")

    # --- TTM ---
    ttm_eps = derived_eps(NDX_LEVEL, TTM_PE)
    lines.append("=" * 60)
    lines.append(f"一、TTM（滚动市盈率）口径　来源：worldperatio(基于QQQ) 2026-09-10")
    lines.append("=" * 60)
    lines.append(f"当前 TTM P/E：{TTM_PE}")
    lines.append(f"反推 TTM EPS：{ttm_eps:,.1f}  （= {NDX_LEVEL:,.2f} / {TTM_PE}）")
    lines.append(f"{'时间窗口':<10}{'历史均值μ':>10}{'σ':>8}{'当前分位':>10}   估值温度")
    for name, (mu, lo, hi) in TTM_BANDS.items():
        sigma = sigma_from_range(lo, hi)
        pct = normal_percentile(TTM_PE, mu, sigma)
        lines.append(f"{name:<12}{mu:>9.2f}{sigma:>8.2f}{pct:>9.0f}%   {temperature_label(pct)}")

    # --- Forward ---
    fwd_eps = derived_eps(NDX_LEVEL, FWD_PE)
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"二、Forward（前瞻市盈率）口径　来源：WSJ 2026-09-04（晨报口径）")
    lines.append("=" * 60)
    lines.append(f"当前 Forward P/E：{FWD_PE}")
    lines.append(f"反推 Forward EPS：{fwd_eps:,.1f}  （= {NDX_LEVEL:,.2f} / {FWD_PE}）")
    lines.append(f"{'时间窗口':<10}{'历史均值μ':>10}{'σ':>8}{'当前分位':>10}   估值温度")
    for name, (mu, lo, hi) in FWD_BANDS.items():
        sigma = sigma_from_range(lo, hi)
        pct = normal_percentile(FWD_PE, mu, sigma)
        lines.append(f"{name:<12}{mu:>9.2f}{sigma:>8.2f}{pct:>9.0f}%   {temperature_label(pct)}")

    lines.append("")
    lines.append("注：分位为正态近似（仅有 μ/σ，非真实日度序列）；两口径 PE 数值不可直接互比。")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render())
