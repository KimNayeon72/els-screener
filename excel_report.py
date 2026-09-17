# -*- coding: utf-8 -*-
"""
그 주에 조회된 ELS 상품 전체(키움+NH, 기초자산 2개 구성)를 엑셀로 정리하고,
최종 추천 조건(수익률 15%+ AND 2년간 배리어 이하 하락 이력 없음)을 만족하는
행에 색을 칠한다.
"""

import os
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from config import OUTPUT_DIR, MIN_ANNUAL_YIELD_PCT, DEFAULT_FIRST_BARRIER_PCT

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF")
BODY_FONT = Font(name="Arial")
RECOMMEND_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
RECOMMEND_FONT = Font(name="Arial", bold=True, color="006100")

COLUMNS = [
    "판매사", "종목명", "기초자산1", "기초자산2",
    "수익률(세전,연환산 %)", "최대손실률(%)", "적용배리어(%, 근사)",
    "만기", "만기일", "발행일(추정)", "청약마감일",
    "수익률15%이상", "배리어2년내하락이력없음", "판정가능여부", "최종추천", "공시URL",
]


def build_report(rows: list, output_path: str = None) -> str:
    """rows: 각 상품에 스크리닝 결과가 합쳐진 dict 리스트.
    krx_client._parse_row()가 만드는 스키마 + underlying_price_checker가
    추가하는 '배리어이하하락이력있음' / '판정가능' 키를 기대한다.
    """
    if output_path is None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, f"ELS_스크리닝_{date.today().isoformat()}.xlsx")

    wb = Workbook()
    ws = wb.active
    ws.title = "ELS 스크리닝 결과"

    for col_idx, header in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for r, item in enumerate(rows, start=2):
        underlyings = item.get("기초자산", [])
        u1 = underlyings[0] if len(underlyings) > 0 else ""
        u2 = underlyings[1] if len(underlyings) > 1 else ""

        yield_pct = item.get("수익률(세전, 연환산)")
        yield_ok = bool(yield_pct is not None and yield_pct >= MIN_ANNUAL_YIELD_PCT)
        barrier_ok = not item.get("배리어이하하락이력있음", True)
        judgeable = item.get("판정가능", False)
        final_recommend = bool(yield_ok and barrier_ok and judgeable)
        applied_barrier = item.get("첫조기상환배리어(%)") or DEFAULT_FIRST_BARRIER_PCT

        values = [
            item.get("판매사", ""),
            item.get("종목명", ""),
            u1,
            u2,
            yield_pct if yield_pct is not None else "확인불가",
            item.get("최대손실률(%)", ""),
            f"{applied_barrier} (근사값)",
            item.get("만기", ""),
            item.get("만기일", ""),
            item.get("발행일(추정)", ""),
            item.get("청약마감일", ""),
            "O" if yield_ok else "X",
            "O" if barrier_ok else ("확인불가" if not judgeable else "X"),
            "O" if judgeable else "X",
            "★추천" if final_recommend else "",
            item.get("공시URL", ""),
        ]

        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col_idx, value=val)
            cell.font = RECOMMEND_FONT if final_recommend else BODY_FONT
            if final_recommend:
                cell.fill = RECOMMEND_FILL

    for col_idx, header in enumerate(COLUMNS, start=1):
        max_len = max([len(str(header))] + [len(str(ws.cell(row=r, column=col_idx).value or ""))
                                             for r in range(2, ws.max_row + 1)])
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 45)

    ws.freeze_panes = "A2"
    wb.save(output_path)
    return output_path
