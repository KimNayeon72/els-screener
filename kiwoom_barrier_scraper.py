# -*- coding: utf-8 -*-
"""
키움증권 ELS/ELB 페이지(비로그인 공개 페이지)에서 상품별 실제 조기상환
배리어 구조(예: "80-80-75-75-70-65 KI20")를 가져와, 기초자산 조합을 키로
하는 조회용 dict를 만든다.

이 페이지의 "청약예정 상품" 카드 섹션은 자바스크립트 없이도 그대로 응답에
포함되는 정적 HTML이라 requests만으로 가져올 수 있다 (2026-09-18 확인).
다만 증권사가 페이지 구조를 바꾸면 정규식이 깨질 수 있으니, 파싱에 실패한
상품은 조용히 None을 반환해서 상위 로직이 '확인불가'로 처리하게 한다.

주의: NH투자증권은 robots.txt가 자동 접근을 막고 있어 이 방식이 통하지
않는다. NH 상품의 배리어는 이 스크립트로 확인할 수 없다.
"""

import re
import requests
from bs4 import BeautifulSoup

KIWOOM_ELS_URL = "https://www3.kiwoom.com/wm/edl/es010/edlElsView"

# "3년/6개월 (80-80-75-75-70-65) KI20" 같은 패턴에서 배리어 숫자열과 KI값을 추출
_BARRIER_RE = re.compile(r"\(([\d\-()A-Za-z]+)\)\s*KI\s*(\d+)")


def fetch_kiwoom_barrier_map() -> dict:
    """{frozenset(기초자산1, 기초자산2): {"첫조기상환배리어": 80.0, "KI": 20.0, "원문": "..."}} 형태로 반환.
    페이지 접근이나 파싱에 실패하면 빈 dict를 반환한다 (상위 로직은 이 경우
    모든 키움 상품을 '확인불가'로 처리하게 된다).
    """
    try:
        resp = requests.get(
            KIWOOM_ELS_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception:
        return {}

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text("\n")
    except Exception:
        return {}

    return _parse_barrier_map(text)


def _parse_barrier_map(text: str) -> dict:
    """페이지 전체 텍스트에서 '기초자산 ... 유형 ... (배리어구조) KI숫자' 블록을
    하나씩 찾아 매핑을 만든다. 카드 하나의 텍스트 블록은 대략 다음과 같은 순서:
        ... 기초자산<이름1>, <이름2> ... 유형 ... (80-80-75-75-70-65) KI20 ...
    """
    result = {}
    # '기초자산' 등장 지점마다, 그 다음 500자 이내에서 배리어 패턴을 찾는다.
    for m in re.finditer(r"기초자산([^\n]+)", text):
        assets_raw = m.group(1).strip()
        assets = tuple(a.strip() for a in assets_raw.split(",") if a.strip())
        if len(assets) < 1:
            continue

        window = text[m.end(): m.end() + 500]
        bm = _BARRIER_RE.search(window)
        if not bm:
            continue

        barrier_sequence = bm.group(1)
        first_token = barrier_sequence.split("-")[0]
        first_digits = re.match(r"\d+", first_token)
        if not first_digits:
            continue
        first_barrier_pct = float(first_digits.group())

        key = frozenset(assets)
        result[key] = {
            "첫조기상환배리어": first_barrier_pct,
            "KI": float(bm.group(2)),
            "원문": f"{barrier_sequence} KI{bm.group(2)}",
        }
    return result


def lookup_barrier(barrier_map: dict, underlyings: list):
    """기초자산 리스트(순서 무관)로 배리어 맵에서 매칭을 찾는다."""
    key = frozenset(underlyings)
    return barrier_map.get(key)
