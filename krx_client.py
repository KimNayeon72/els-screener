# -*- coding: utf-8 -*-
"""
KRX 파생결합증권 통합정보플랫폼(data.krx.co.kr)에서
현재 청약중인 ELS/ELB 상품 전체 목록을 가져온다.

필드 매핑은 사용자가 제공한 실제 응답(HAR 캡처, bld=MDCSTAT17302_OUT)을
기준으로 확정된 값이다.

실제 응답 필드 예시:
{
  "ISU_NM": "N2 ELS 427",            # 종목명
  "SUBS_END_DD": "2026.09.17",       # 청약마감일
  "DCS_SECU_TP_NM": "수익한도제한형", # 증권유형
  "RISK_INDIC_VAL": "1",             # 위험지표(1=매우높음~6=매우낮음)
  "DCS_ULY_CNT": "2",                # 기초자산개수  <- 이 값으로 2개짜리만 필터
  "DCS_ULY_NM": "LG전자, SK하이닉스", # 기초자산명(쉼표구분)
  "EXP_DD": "2029.09.18",            # 만기일
  "ISU_EXP_YM": "3년",               # 발행만기(문자열, "6개월"/"3년" 등)
  "ISU_CURR_NM": "원화",             # 통화
  "COND_YD": "24.300%",              # 조건 충족시 수익률(세전, 연환산)
  "MAX_LOSS_RT": "-100%",            # 조건 미충족시 최대손실률
  "ISUR_NM": "NH투자증권",           # 발행사
  "SALE_COM_NM": "NH투자증권",       # 판매사  <- 이 값으로 키움/NH 필터
  "ISU_DISCLS_URL": "http://dart.fss.or.kr/..."  # DART 공시(투자설명서) 링크
}

주의: 이 데이터에는 '첫 조기상환 배리어(%)' 값이 직접 나오지 않는다.
정확한 배리어는 ISU_DISCLS_URL의 DART 공시(투자설명서/KID)를 열어봐야 하며,
이 스크립트는 1차적으로 config.DEFAULT_FIRST_BARRIER_PCT를 근사값으로 사용한다.
"""

import json
import os
import re
import requests
from datetime import datetime, timedelta

from config import KRX_GENERATE_URL, KRX_BLD, TARGET_DEALERS, OUTPUT_DIR


def fetch_els_products():
    """KRX에서 청약중인 전체 ELS/ELB를 가져와 판매사가 키움/NH인 것만 반환한다."""
    if KRX_BLD.startswith("TODO"):
        raise RuntimeError("config.py의 KRX_BLD 값이 설정되지 않았습니다.")

    payload = {
        "bld": KRX_BLD,
        "locale": "ko_KR",
        "csvxls_isNo": "false",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd?screenId=MDCSTAT173",
    }
    resp = requests.post(KRX_GENERATE_URL, data=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "krx_raw_sample.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    rows = data.get("output", [])
    products = []
    for row in rows:
        parsed = _parse_row(row)
        if parsed and parsed["판매사"] in TARGET_DEALERS:
            products.append(parsed)
    return products


def _parse_row(row: dict):
    try:
        dealer = row.get("SALE_COM_NM")
        name = row.get("ISU_NM")
        if not dealer or not name:
            return None

        underlying_raw = row.get("DCS_ULY_NM", "")
        underlyings = [u.strip() for u in underlying_raw.split(",") if u.strip()]

        yield_pct = _pct_to_float(row.get("COND_YD"))
        max_loss_pct = _pct_to_float(row.get("MAX_LOSS_RT"))
        maturity = row.get("ISU_EXP_YM")
        exp_dd = row.get("EXP_DD")
        issue_date = _estimate_issue_date(exp_dd, maturity)

        return {
            "판매사": dealer,
            "종목명": name,
            "기초자산": underlyings,
            "수익률(세전, 연환산)": yield_pct,
            "최대손실률(%)": max_loss_pct,
            "첫조기상환배리어(%)": None,  # DART 공시 파싱 전까지는 config 기본값 사용
            "만기": maturity,
            "만기일": exp_dd,
            "발행일(추정)": issue_date,
            "청약마감일": row.get("SUBS_END_DD"),
            "공시URL": row.get("ISU_DISCLS_URL"),
            "원문": row,
        }
    except Exception:
        return None


def _pct_to_float(value):
    if not value:
        return None
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


_MATURITY_RE = re.compile(r"(\d+)\s*(년|개월)")


def _estimate_issue_date(exp_dd: str, maturity_str: str):
    """만기일(EXP_DD)과 발행만기(예: '3년','6개월')로 발행일을 역산 추정한다.
    실제 발행일과 며칠 오차가 있을 수 있다 (영업일/휴장일 미반영).
    """
    if not exp_dd or not maturity_str:
        return None
    try:
        exp_date = datetime.strptime(exp_dd, "%Y.%m.%d")
    except ValueError:
        return None

    m = _MATURITY_RE.search(maturity_str)
    if not m:
        return None
    num, unit = int(m.group(1)), m.group(2)
    days = num * 365 if unit == "년" else num * 30
    issue_date = exp_date - timedelta(days=days)
    return issue_date.strftime("%Y-%m-%d")
