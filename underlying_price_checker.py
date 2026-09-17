# -*- coding: utf-8 -*-
"""
기초자산별 최근 2년 일별 종가를 가져와서, 상품 조회일(전일 종가 기준)로부터
과거 2년 동안 '최초 발행가 대비 첫 조기상환 배리어(%)' 이하로 하락한 적이
있는지 계산한다.

방법론 상의 중요한 단순화:
- 실제 ELS는 상품별로 '기준가(최초기준가)'가 따로 산정되고, 배리어는 그 기준가
  대비 비율로 정의된다. 이 스크립트는 상품의 정확한 최초기준가를 구할 수 없는
  경우, 기초자산의 발행일 종가를 최초기준가로 근사한다. 실제 발행사 고시
  기준가와는 소폭 차이가 있을 수 있으므로, 최종 매수 전 반드시 상품 상세페이지의
  실제 기준가로 재확인해야 한다.
"""

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from config import ASSET_TICKER_MAP, LOOKBACK_YEARS, DEFAULT_FIRST_BARRIER_PCT


def check_product_barrier_history(product: dict) -> dict:
    """상품 하나에 대해 기초자산별 배리어 하회 이력을 확인한다.

    반환:
    {
        "판정가능": True/False,   # 모든 기초자산의 티커를 알고 있어야 True
        "배리어이하하락이력있음": True/False,
        "상세": {자산명: {"티커":..., "하락이력":..., "최저비율(%)":...}}
    }
    """
    detail = {}
    all_known = True
    any_breach = False

    barrier_pct = product.get("첫조기상환배리어(%)") or DEFAULT_FIRST_BARRIER_PCT

    for asset_name in product["기초자산"]:
        ticker = ASSET_TICKER_MAP.get(asset_name)
        if not ticker:
            all_known = False
            detail[asset_name] = {"티커": None, "하락이력": None, "최저비율(%)": None}
            continue

        breached, min_ratio = _check_single_asset(ticker, product.get("발행일(추정)"), barrier_pct)
        detail[asset_name] = {
            "티커": ticker,
            "하락이력": breached,
            "최저비율(%)": min_ratio,
        }
        if breached:
            any_breach = True

    return {
        "판정가능": all_known,
        "배리어이하하락이력있음": any_breach,
        "상세": detail,
    }


def _check_single_asset(ticker: str, issue_date_str, barrier_pct: float):
    """단일 기초자산의 2년 종가를 받아 배리어 하회 이력을 계산한다."""
    end = datetime.today()
    start = end - timedelta(days=365 * LOOKBACK_YEARS + 10)

    hist = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                        end=end.strftime("%Y-%m-%d"), progress=False)
    if hist.empty:
        return None, None

    closes = hist["Close"].dropna()

    # 최초기준가 근사: 발행일 종가가 있으면 그것을, 없으면 조회기간 첫 종가를 사용
    base_price = None
    if issue_date_str:
        try:
            issue_dt = pd.to_datetime(issue_date_str)
            nearest = closes.index[closes.index.get_indexer([issue_dt], method="nearest")[0]]
            base_price = float(closes.loc[nearest])
        except Exception:
            base_price = None
    if base_price is None:
        base_price = float(closes.iloc[0])

    ratio_series = closes / base_price * 100.0
    min_ratio = float(ratio_series.min())
    breached = min_ratio <= barrier_pct

    return breached, round(min_ratio, 2)
