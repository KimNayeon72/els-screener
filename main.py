# -*- coding: utf-8 -*-
"""
매주 월요일 실행되는 ELS 스크리닝 메인 파이프라인.

흐름:
1) KRX에서 키움/NH가 판매중인 ELS 상품 목록을 가져온다
2) 기초자산이 정확히 2개인 상품만 남긴다
3) 청약마감일이 이미 지난 상품(숙려기간 등으로 더 이상 청약 불가능한 상품)을
   제외한다
4) 수익률(세전, 연환산) 15% 이상인 상품만 남긴다 — 이 기준에 못 미치는 상품은
   엑셀에도 아예 나오지 않는다
5) 남은 상품에 대해 키움증권 공식 페이지에서 실제 첫조기상환배리어(%),
   전체 배리어 구조, 조기상환 주기를 매칭한다. 매칭 안 되는 상품(키움 매칭
   실패, 모든 NH 상품)은 부정확한 기본값을 적용하지 않고 '확인불가'로 남겨
   자동추천에서 제외한다.
6) 배리어가 확인된 상품에 대해서만 최근 2년 종가로 배리어 하회 이력을 계산한다
7) 결과를 엑셀로 정리(최종 조건을 만족하는 상품은 색으로 표시)

결과 전달 방식: 이메일을 보내지 않고, output/ 폴더의 엑셀 파일을
GitHub Actions의 'Artifacts'에 올려두기만 합니다.
"""

import sys
from datetime import datetime

from krx_client import fetch_els_products, enrich_with_kiwoom_barrier
from kiwoom_barrier_scraper import fetch_kiwoom_barrier_map
from underlying_price_checker import check_product_barrier_history
from excel_report import build_report
from config import REQUIRED_ASSET_COUNT, MIN_ANNUAL_YIELD_PCT


def _subscription_still_open(product: dict) -> bool:
    """청약마감일이 오늘이거나 아직 지나지 않았으면 True."""
    deadline_str = product.get("청약마감일")
    if not deadline_str:
        return True  # 날짜 정보가 없으면 일단 포함시키고 사람이 확인하게 둠
    try:
        deadline = datetime.strptime(deadline_str, "%Y.%m.%d").date()
    except ValueError:
        return True
    return deadline >= datetime.today().date()


def run():
    print("[1/6] KRX에서 ELS 상품 목록 가져오는 중...")
    products = fetch_els_products()
    print(f"  -> 키움/NH 상품 {len(products)}건 조회됨")

    print(f"[2/6] 기초자산 {REQUIRED_ASSET_COUNT}개 구성 상품만 필터링...")
    two_asset_products = [p for p in products if len(p.get("기초자산", [])) == REQUIRED_ASSET_COUNT]
    print(f"  -> {len(two_asset_products)}건 남음")

    print("[3/6] 청약마감일이 지난 상품 제외 중...")
    two_asset_products = [p for p in two_asset_products if _subscription_still_open(p)]
    print(f"  -> {len(two_asset_products)}건 남음 (청약 가능한 상품만)")

    print(f"[4/6] 수익률 {MIN_ANNUAL_YIELD_PCT}% 미만 상품 제외 중...")
    candidates = [
        p for p in two_asset_products
        if (p.get("수익률(세전, 연환산)") or 0) >= MIN_ANNUAL_YIELD_PCT
    ]
    print(f"  -> {len(candidates)}건 남음 (이 상품들만 엑셀에 포함됩니다)")

    if not candidates:
        print("조건을 만족하는 상품이 없어 종료합니다.")
        build_report([])
        return

    print("[5/6] 키움증권 공식 페이지에서 실제 배리어 매칭 중...")
    kiwoom_barrier_map = fetch_kiwoom_barrier_map()
    print(f"  -> 키움 페이지에서 {len(kiwoom_barrier_map)}개 기초자산 조합의 배리어 구조 확인됨")
    candidates = enrich_with_kiwoom_barrier(candidates, kiwoom_barrier_map)

    print("[6/6] 배리어 하락 이력 확인 중 (시간이 걸릴 수 있음)...")
    for p in candidates:
        result = check_product_barrier_history(p)
        p["배리어이하하락이력있음"] = result["배리어이하하락이력있음"]
        p["판정가능"] = result["판정가능"]
        p["기초자산상세"] = result["상세"]

    recommend_count = sum(
        1 for p in candidates
        if p.get("판정가능") and not p.get("배리어이하하락이력있음")
    )
    print(f"최종 추천 상품: {recommend_count}건. 엑셀 생성 중...")

    xlsx_path = build_report(candidates)
    print(f"완료. 파일: {xlsx_path}")
    print("이 파일은 GitHub Actions 실행 결과의 'Artifacts'에서 다운로드할 수 있습니다.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"오류 발생: {e}", file=sys.stderr)
        raise
