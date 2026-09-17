# -*- coding: utf-8 -*-
"""
매주 월요일 실행되는 ELS 스크리닝 메인 파이프라인.

흐름:
1) KRX에서 키움/NH가 판매중인 ELS 상품 목록을 가져온다
2) 기초자산이 정확히 2개인 상품만 남긴다
3) 각 상품의 기초자산에 대해 최근 2년 종가를 가져와
   '발행 이후 첫 조기상환 배리어 이하로 내려간 적 있는지' 계산한다
4) 연 수익률 15% 이상 + 배리어 하락 이력 없음 을 모두 만족하는 상품을 '추천'으로 표시
5) 이번 주 조회된 상품 전체를 엑셀로 정리(추천 상품은 색으로 표시)

결과 전달 방식: 이메일을 보내지 않고, output/ 폴더의 엑셀 파일을
GitHub Actions의 'Artifacts'(첨부파일 보관함)에 올려두기만 합니다.
GitHub 저장소 > Actions 탭 > 해당 실행(run) > 하단 Artifacts에서
매주 직접 다운로드하시면 됩니다.
"""

import sys

from krx_client import fetch_els_products
from underlying_price_checker import check_product_barrier_history
from excel_report import build_report
from config import REQUIRED_ASSET_COUNT


def run():
    print("[1/4] KRX에서 ELS 상품 목록 가져오는 중...")
    products = fetch_els_products()
    print(f"  -> 키움/NH 상품 {len(products)}건 조회됨")

    print(f"[2/4] 기초자산 {REQUIRED_ASSET_COUNT}개 구성 상품만 필터링...")
    two_asset_products = [p for p in products if len(p.get("기초자산", [])) == REQUIRED_ASSET_COUNT]
    print(f"  -> {len(two_asset_products)}건 남음")

    if not two_asset_products:
        print("대상 상품이 없어 종료합니다.")
        return

    print("[3/4] 기초자산별 2년 배리어 하락 이력 확인 중 (시간이 걸릴 수 있음)...")
    enriched = []
    for p in two_asset_products:
        result = check_product_barrier_history(p)
        p["배리어이하하락이력있음"] = result["배리어이하하락이력있음"]
        p["판정가능"] = result["판정가능"]
        p["기초자산상세"] = result["상세"]
        enriched.append(p)

    recommend_count = sum(
        1 for p in enriched
        if p["판정가능"]
        and not p["배리어이하하락이력있음"]
        and (p.get("수익률(세전, 연환산)") or 0) >= 15.0
    )
    print(f"[4/4] 엑셀 생성 중... (최종 추천 상품: {recommend_count}건)")

    xlsx_path = build_report(enriched)
    print(f"완료. 파일: {xlsx_path}")
    print("이 파일은 GitHub Actions 실행 결과의 'Artifacts'에서 다운로드할 수 있습니다.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"오류 발생: {e}", file=sys.stderr)
        raise
