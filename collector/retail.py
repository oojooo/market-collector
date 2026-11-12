"""리테일 상품 데일리용 보조 수집 — retail.json.

메이저 목록 중 Claude 웹 도구로 접근 가능한 곳(한경·중앙)의 섹션 헤드라인을 미리 수집한다.
조선비즈·연합·매경은 차단 도메인이라 이 수집기로도 대체하지 않는다(차단 우회 금지 원칙).
시장 이슈의 정형 수치(지수·금리·공시)는 market.json을 함께 읽으면 된다.
"""
from . import util

PAGES = {
    "hankyung_finance_1212": "https://www.hankyung.com/economy/1212",
    "hankyung_finance_1213": "https://www.hankyung.com/economy/1213",
    "joongang_money": "https://www.joongang.co.kr/money/finance",
}


def pages():
    out = {}
    for k, u in PAGES.items():
        out[k] = {"url": u, "excerpt": util.firecrawl(u, 5000)}
    return {"status": "ok", "source": "한경·중앙 섹션 목록(Firecrawl)", "pages": out}


def collect():
    errors = []
    out = {"pages": util.section(pages, errors, "pages")}
    payload = util.finalize("retail", out, errors)
    payload["meta"]["note"] = (
        "이 JSON은 보조 자료 — 상품 뉴스 본 취재는 브리핑 작업의 WebSearch가 주력. "
        "시장 이슈 수치는 market.json 참조. 차단 도메인 원문은 수집하지 않음."
    )
    return payload
