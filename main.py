# -*- coding: utf-8 -*-
"""
매주 월요일 실행되는 ELS 스크리닝 메인 파이프라인.

흐름:
1) KRX에서 키움/NH가 판매중인 ELS 상품 목록을 가져온다
2) 기초자산이 정확히 2개인 상품만 남긴다
3) 그중 수익률(세전, 연환산) 15% 이상인 상품만 '배리어 확인 대상'으로 추린다
   (수익률 미달 상품은 어차피 추천 대상이 될 수 없으므로 배리어 조회를 생략해
   실행 시간과 외부 API 호출을 아낀다)
4) 대상 상품에 대해 키움증권 공식 페이지에서 실제 첫조기상환배리어(%)를
   매칭한다. 매칭 안 되는 상품(키움 매칭 실패, 모든 NH 상품)은 부정확한
   기본값을 적용하지 않고 '확인불가'로 남겨 자동추천에서 제외한다.
5) 배리어가 확인된 상품에 대해서만 최근 2년 종가로 배리어 하회 이력을 계산한다
6) 이번 주 조회된 상품 전체(기초자산 2개 구성)를 엑셀로 정리(추천 상품은 색으로 표시)

결과 전달 방식: 이메일을 보내지 않고, output/ 폴더의 엑셀 파일을
GitHub Actions의 'Artifacts'에 올려두기만 합니다.
"""

import sys

from krx_client import fetch_els_products, enrich_with_kiwoom_barrier
from kiwoom_barrier_scraper import fetch_kiwoom_barrier_map
from underlying_price_checker import check_product_barrier_history
from excel_report import build_report
from config import REQUIRED_ASSET_COUNT, MIN_ANNUAL_YIELD_PCT


def run():
    print("[1/5] KRX에서 ELS 상품 목록 가져오는 중...")
    products = fetch_els_products()
    print(f"  -> 키움/NH 상품 {len(products)}건 조회됨")

    print(f"[2/5] 기초자산 {REQUIRED_ASSET_COUNT}개 구성 상품만 필터링...")
    two_asset_products = [p for p in products if len(p.get("기초자산", [])) == REQUIRED_ASSET_COUNT]
    print(f"  -> {len(two_asset_products)}건 남음")

    if not two_asset_products:
        print("대상 상품이 없어 종료합니다.")
        return

    print(f"[3/5] 수익률 {MIN_ANNUAL_YIELD_PCT}% 이상 상품만 배리어 확인 대상으로 추리는 중...")
    candidates = [
        p for p in two_asset_products
        if (p.get("수익률(세전, 연환산)") or 0) >= MIN_ANNUAL_YIELD_PCT
    ]
    print(f"  -> {len(candidates)}건이 수익률 조건 통과 (배리어 확인 진행)")

    print("[4/5] 키움증권 공식 페이지에서 실제 배리어 매칭 중...")
    kiwoom_barrier_map = fetch_kiwoom_barrier_map()
    print(f"  -> 키움 페이지에서 {len(kiwoom_barrier_map)}개 기초자산 조합의 배리어 구조 확인됨")
    two_asset_products = enrich_with_kiwoom_barrier(two_asset_products, kiwoom_barrier_map)

    print("[5/5] 배리어 확인 대상 상품의 2년 배리어 하락 이력 확인 중 (시간이 걸릴 수 있음)...")
    candidate_ids = {id(p) for p in candidates}
    for p in two_asset_products:
        if id(p) not in candidate_ids:
            # 수익률 미달 상품은 배리어 조회를 생략 (API 호출 절약)
            p["판정가능"] = False
            p["배리어이하하락이력있음"] = None
            continue
        result = check_product_barrier_history(p)
        p["배리어이하하락이력있음"] = result["배리어이하하락이력있음"]
        p["판정가능"] = result["판정가능"]
        p["기초자산상세"] = result["상세"]

    recommend_count = sum(
        1 for p in two_asset_products
        if p.get("판정가능")
        and not p.get("배리어이하하락이력있음")
        and (p.get("수익률(세전, 연환산)") or 0) >= MIN_ANNUAL_YIELD_PCT
    )
    print(f"최종 추천 상품: {recommend_count}건. 엑셀 생성 중...")

    xlsx_path = build_report(two_asset_products)
    print(f"완료. 파일: {xlsx_path}")
    print("이 파일은 GitHub Actions 실행 결과의 'Artifacts'에서 다운로드할 수 있습니다.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"오류 발생: {e}", file=sys.stderr)
        raise
