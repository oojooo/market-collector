"""데일리 마켓 브리프용 수집 — market.json.

소스 맵(기존 맥북 MCP 체계를 그대로 이식):
  FRED API(미 지수·금리 공식치) · ECOS(국고채·회사채·CD) · KRX 공공데이터포털(지수·관심 3사)
  · OpenDART(관심 3사 공시) · TradingEconomics 7페이지(Firecrawl, 당일 호가·재정환율)
  · 네이버페이 증권 리서치 목록+상세(Firecrawl) · 한경 컨센서스·종목페이지(Playwright, 로그인 불필요 영역만)
뉴스(마감 기사·정산가·하우스 코멘트)는 브리핑 예약 작업이 WebSearch/WebFetch로 직접 수행.
"""
import datetime
import os
import re
from urllib.parse import unquote

from . import util

FRED_SERIES = ["SP500", "NASDAQCOM", "DJIA", "DGS2", "DGS10", "DGS30", "DFF", "DFII30", "T10Y2Y"]

ECOS_ITEMS = {
    "010210000": "국고채10년",
    "010200000": "국고채3년",
    "010230000": "국고채30년",
    "010300000": "회사채AA-",
    "010502000": "CD91일",
}

STOCKS = [("005930", "삼성전자"), ("000660", "SK하이닉스"), ("042700", "한미반도체")]
DART_CORPS = [("00126380", "삼성전자"), ("00164779", "SK하이닉스"), ("00161383", "한미반도체")]

TE_PAGES = {
    "us30y": "https://tradingeconomics.com/united-states/30-year-bond-yield",
    "us10y": "https://tradingeconomics.com/united-states/10-year-bond-yield",
    "gold": "https://tradingeconomics.com/commodity/gold",
    "dxy": "https://tradingeconomics.com/united-states/currency",
    "usdkrw": "https://tradingeconomics.com/south-korea/currency",
    "usdjpy": "https://tradingeconomics.com/japan/currency",
    "usdbrl": "https://tradingeconomics.com/brazil/currency",
}

NAVER_LISTS = {
    "daily": "https://m.stock.naver.com/investment/research/daily",
    "invest": "https://m.stock.naver.com/investment/research/invest",
    "industry": "https://m.stock.naver.com/investment/research/industry",
    "economy": "https://m.stock.naver.com/investment/research/economy",
}


def fred():
    key = os.environ["FRED_API_KEY"]
    out = {}
    for sid in FRED_SERIES:
        js = util.get_json(
            "https://api.stlouisfed.org/fred/series/observations",
            {"series_id": sid, "api_key": key, "file_type": "json", "sort_order": "desc", "limit": 6},
        )
        obs = [o for o in js.get("observations", []) if o.get("value") not in (".", None)][:2]
        out[sid] = [{"date": o["date"], "value": o["value"]} for o in obs]
    return {"status": "ok", "source": "FRED API(공식치 — 지수·일부 금리는 1일 지연)", "series": out}


def ecos():
    key = os.environ["ECOS_API_KEY"]
    end = util.ymd(util.now_kst())
    start = util.ymd(util.now_kst() - datetime.timedelta(days=12))
    out = {}
    for code, label in ECOS_ITEMS.items():
        js = util.get_json(
            f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/30/817Y002/D/{start}/{end}/{code}"
        )
        rows = (js.get("StatisticSearch") or {}).get("row") or []
        if not rows and js.get("RESULT"):
            raise RuntimeError(f"ECOS {label}: {js['RESULT'].get('MESSAGE')}")
        out[label] = [{"date": r["TIME"], "value": r["DATA_VALUE"]} for r in rows[-2:]]
    return {"status": "ok", "source": "한국은행 ECOS(시장금리 817Y002, 최근 2영업일)", "items": out}


def _datago_items(service: str, op: str, params: dict):
    base = f"https://apis.data.go.kr/1160100/service/{service}/{op}"
    p = {"serviceKey": os.environ["DATA_GO_KR_KEY"], "resultType": "json", "pageNo": 1, **params}
    js = util.get_json(base, p)
    items = ((((js.get("response") or {}).get("body") or {}).get("items")) or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]
    items.sort(key=lambda x: x.get("basDt", ""), reverse=True)
    return items


def krx():
    idx = {}
    for name in ("코스피", "코스닥"):
        items = _datago_items("GetMarketIndexInfoService", "getStockMarketIndex", {"numOfRows": 6, "idxNm": name})
        idx[name] = [
            {"date": i.get("basDt"), "close": i.get("clpr"), "chg": i.get("vs"), "chg_pct": i.get("fltRt")}
            for i in items[:2]
        ]
    stocks = {}
    for code, nm in STOCKS:
        items = _datago_items("GetStockSecuritiesInfoService", "getStockPriceInfo", {"numOfRows": 8, "likeSrtnCd": code})
        items = [i for i in items if i.get("srtnCd", "").endswith(code)]
        stocks[nm] = [
            {
                "date": i.get("basDt"), "close": i.get("clpr"), "chg": i.get("vs"),
                "chg_pct": i.get("fltRt"), "volume": i.get("trqu"), "mktcap": i.get("mrktTotAmt"),
            }
            for i in items[:2]
        ]
    return {"status": "ok", "source": "KRX(공공데이터포털 금융위 시세 — 보통 전 영업일까지)", "index": idx, "stocks": stocks}


def dart():
    key = os.environ["DART_API_KEY"]
    wd = util.now_kst().weekday()  # 월=0
    back = {0: 3, 5: 1, 6: 2}.get(wd, 1)  # 월→금, 주중→전일
    bgn = util.ymd(util.now_kst() - datetime.timedelta(days=back))
    out = {}
    for corp, nm in DART_CORPS:
        js = util.get_json(
            "https://opendart.fss.or.kr/api/list.json",
            {"crtfc_key": key, "corp_code": corp, "bgn_de": bgn, "page_count": 20},
        )
        st = js.get("status")
        if st == "013":
            out[nm] = []  # 신규 공시 없음
        elif st == "000":
            out[nm] = [
                {
                    "date": x.get("rcept_dt"), "title": x.get("report_nm"), "filer": x.get("flr_nm"),
                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={x.get('rcept_no')}",
                }
                for x in js.get("list", [])
            ]
        else:
            raise RuntimeError(f"DART {nm}: {st} {js.get('message')}")
    return {"status": "ok", "source": "DART(OpenDART)", "bgn_de": bgn, "disclosures": out}


def te():
    pages = {}
    for k, u in TE_PAGES.items():
        pages[k] = {"url": u, "excerpt": util.firecrawl(u, 2600)}

    def first_rate(txt):
        m = re.search(r"(?:Exchange Rate|Actual)\s*\n+\s*([\d,]+\.?\d*)", txt or "")
        try:
            return float(m.group(1).replace(",", "")) if m else None
        except ValueError:
            return None

    krw = first_rate(pages["usdkrw"]["excerpt"])
    jpy = first_rate(pages["usdjpy"]["excerpt"])
    brl = first_rate(pages["usdbrl"]["excerpt"])
    cross = {"usdkrw": krw, "usdjpy": jpy, "usdbrl": brl}
    if krw and jpy:
        cross["krw_per_100jpy"] = round(krw / jpy * 100, 1)
    if krw and brl:
        cross["krw_per_brl"] = round(krw / brl, 1)
    return {
        "status": "ok",
        "source": "TradingEconomics(역외 호가 — 기준일은 각 excerpt 본문의 'on <date>'로 확인)",
        "pages": pages,
        "cross_calc_note": "원/엔(100엔당)=USDKRW÷USDJPY×100 · 원/헤알=USDKRW÷USDBRL — 'TE 국가별 페이지 재정환율(역외 호가)'로 표기",
        "cross_calc": cross,
    }


def naver_research():
    lists = {}
    links = []
    for k, u in NAVER_LISTS.items():
        md = util.firecrawl(u, 6500)
        lists[k] = md
        for m in re.finditer(r"https://m\.stock\.naver\.com/investment/research/\w+/\d+", md):
            if m.group(0) not in links:
                links.append(m.group(0))
    details = []
    for link in links[:6]:  # 목록 상단 6건의 요약 본문 + PDF URL
        md = util.firecrawl(link, 6000)
        pdf = None
        m = re.search(r"https%3A%2F%2Fstock\.pstatic\.net[^)\"&\s]+?\.pdf", md)
        if m:
            pdf = unquote(m.group(0))
        details.append({"url": link, "pdf": pdf, "excerpt": md})
    return {
        "status": "ok",
        "source": "네이버페이 증권 리서치(Firecrawl) — 목록 날짜가 전일이면 캐시 구식으로 간주",
        "lists": lists,
        "details": details,
    }


def hankyung():
    """한경 코리아마켓 — 로그인 불필요 영역(컨센서스 목록·종목페이지)만 Playwright로 수집."""
    from playwright.sync_api import sync_playwright

    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="ko-KR")
        page.goto("https://markets.hankyung.com/consensus", timeout=45000)
        page.wait_for_timeout(4000)
        out["consensus_text"] = page.evaluate("document.body.innerText")[:9000]
        out["consensus_links"] = page.evaluate(
            "Array.from(document.querySelectorAll('a[href*=\"consensus/view\"]'))"
            ".slice(0,60).map(a=>a.getAttribute('href')+' | '+a.textContent.trim().replace(/\\s+/g,' ').slice(0,90))"
        )
        stock_pages = {}
        for code, nm in STOCKS:
            page.goto(f"https://markets.hankyung.com/stock/{code}", timeout=45000)
            page.wait_for_timeout(3000)
            stock_pages[f"{nm}({code})"] = page.evaluate("document.body.innerText")[:1800]
        out["stock_pages"] = stock_pages
        browser.close()
    return {"status": "ok", "source": "한경 코리아마켓(Playwright — 로그인 전용 PDF 원문은 미수집)", **out}


def collect():
    errors = []
    out = {
        "fred": util.section(fred, errors, "fred"),
        "ecos": util.section(ecos, errors, "ecos"),
        "krx": util.section(krx, errors, "krx"),
        "dart": util.section(dart, errors, "dart"),
        "te": util.section(te, errors, "te"),
        "naver_research": util.section(naver_research, errors, "naver_research"),
        "hankyung": util.section(hankyung, errors, "hankyung"),
    }
    return util.finalize("market", out, errors)
