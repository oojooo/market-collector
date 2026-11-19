"""데일리 디지털 브리프(STO·디지털자산)용 보조 수집 — digital.json.

이 브리핑은 뉴스 탐색(WebSearch) 비중이 커서 JSON은 '보조'다:
  - 토큰포스트 최신 브리핑·뉴스 목록(시세·국내 디지털자산 헤드라인)
  - 금융위원회 보도자료 목록(STO·스테이블코인 제도의 1차 출처)
연합뉴스·매일경제·조선비즈 등 Claude 웹 도구 차단 도메인은 이 수집기로도 대체하지 않는다
(차단 우회 금지 원칙 — 해당 매체 원문 확인은 맥북 Chrome이 연결된 날에만 수행).
"""
from . import util

PAGES = {
    "tokenpost_briefing": "https://www.tokenpost.kr/news/briefing",
    # /news/latest 는 없는 주소(404)였음 — 2026-11-19 점검에서 확인, 전체 뉴스 목록으로 교체. 키 이름은 그대로 둔다.
    "tokenpost_latest": "https://www.tokenpost.kr/news",
    "fsc_press": "https://www.fsc.go.kr/no010101",
}


# 페이지별 기사 주소 형식 — 이런 링크가 8개 이상 보여야 목록을 제대로 읽은 것으로 본다
PAGE_OK = {
    "tokenpost_briefing": r"https://www\.tokenpost\.kr/[^)\s]*\d{4,}",
    "tokenpost_latest": r"https://www\.tokenpost\.kr/[^)\s]*\d{4,}",
    "fsc_press": r"https://www\.fsc\.go\.kr/no010101/\d+[^)\s]*",
}


def pages():
    """2026-11-19부터 브라우저(Playwright)로 먼저 읽고, 실패한 페이지만 Firecrawl로 읽는다(크레딧 절감).
    한 곳이 안 열려도 나머지는 싣는다(안 열린 곳은 excerpt가 비고 page_errors에 사유가 남는다)."""
    res = util.fetch_pages(PAGES, PAGE_OK)
    return {"status": "ok", "source": "토큰포스트 목록·금융위 보도자료 목록(수집 경로는 페이지별 via)", **res}


def collect():
    errors = []
    out = {"pages": util.section(pages, errors, "pages")}
    payload = util.finalize("digital", out, errors)
    payload["meta"]["note"] = (
        "이 JSON은 보조 자료 — 본 취재는 브리핑 작업의 WebSearch가 주력. "
        "차단 도메인(연합·매경·조선비즈) 원문은 수집하지 않음."
    )
    return payload
