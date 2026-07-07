# -*- coding: utf-8 -*-
"""项目配置。

这个文件只放稳定配置：基金清单、数据文件名、报告文件名和通用列名。
需要调整对比基金时，优先改这里，不要改下载或统计逻辑。
"""

import os


DATA_DIR = "data"
REPORT_FILE = "report.md"

# 要对比的 A 股纳指 ETF/LOF。
# 元组含义：(公司简称, 基金代码, 报告显示名)
# 数据文件名按“公司简称-基金代码.xlsx”生成。
FUNDS = [
    ("易方达", "159696", "易方达"),
    ("嘉实", "159501", "嘉实"),
    ("国泰", "513100", "国泰"),
    ("广发", "159941", "广发"),
    ("华安", "159632", "华安"),
    ("华泰柏瑞", "513110", "华泰柏瑞"),
    ("汇添富", "159660", "汇添富"),
    ("招商", "159659", "招商"),
    ("博时", "513390", "博时"),
    ("大成", "159513", "大成"),
    ("富国", "513870", "富国"),
    ("华夏", "513300", "华夏"),
]

# 香港上市的参考基金。
# 净值为港币，报告阶段会用 HKDCNY 折成人民币口径。
REF_FUNDS = [("安硕", "02834", "2834.HK")]

# 默认使用 NDX 价格指数：多数纳指100 ETF 合同跟踪标的是价格指数。
# 如需观察含股息再投资效果，可通过 --total-return 切换到 XNDX。
DEFAULT_USE_TOTAL_RETURN = False

INDEX_FILE_XNDX = f"{DATA_DIR}/纳斯达克100指数-XNDX.xlsx"
INDEX_FILE_NDX = f"{DATA_DIR}/纳斯达克100指数-NDX.xlsx"
FX_FILE = f"{DATA_DIR}/美元兑人民币-USDCNY.xlsx"
HKFX_FILE = f"{DATA_DIR}/港币兑人民币-HKDCNY.xlsx"

# 所有下载数据都写成同一套列，报告阶段可以用同一套读取逻辑处理基金、指数和汇率。
DATA_COLUMNS = ["基金代码", "基金名称", "净值日期", "单位净值(元)", "日涨跌", "累计净值(元)", "场内收盘(元)", "场内均价(元)", "场内最高(元)", "场内最低(元)", "溢价率(%)"]
USER_AGENT = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def fund_file(company: str, code: str) -> str:
    return f"{DATA_DIR}/{company}-{code}.xlsx"


def index_file(use_total_return: bool) -> str:
    return INDEX_FILE_XNDX if use_total_return else INDEX_FILE_NDX
