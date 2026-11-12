"""공용 유틸 — 시간, HTTP, Firecrawl, 섹션 래퍼, 저장."""
import datetime
import json
import os
import pathlib
import re
import time
import urllib.parse

import requests

KST = datetime.timezone(datetime.timedelta(hours=9))
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
UA = {"User-Agent": "daily-brief-collector (personal use)"}


def now_kst() -> datetime.datetime:
    return datetime.datetime.now(KST)


def today_kst() -> str:
    return now_kst().strftime("%Y-%m-%d")


def ymd(d: datetime.datetime) -> str:
    return d.strftime("%Y%m%d")


def get_json(url, params=None, timeout=30):
    r = requests.get(url, params=params, timeout=timeout, headers=UA)
    r.raise_for_status()
    return r.json()


_last_fc = 0.0


def firecrawl(url: str, max_chars: int = 4000, _retry: bool = True) -> str:
    """Firecrawl scrape API. 분당 한도를 고려해 호출 간 최소 6초 간격, 429면 25초 후 1회 재시도."""
    global _last_fc
    key = os.environ["FIRECRAWL_API_KEY"]
    wait = 6 - (time.time() - _last_fc)
    if wait > 0:
        time.sleep(wait)
    _last_fc = time.time()
    r = requests.post(
        "https://api.firecrawl.dev/v1/scrape",
        headers={"Authorization": f"Bearer {key}"},
        json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
        timeout=90,
    )
    if r.status_code == 429 and _retry:
        time.sleep(25)
        return firecrawl(url, max_chars, _retry=False)
    r.raise_for_status()
    md = (r.json().get("data") or {}).get("markdown") or ""
    return md[:max_chars]


# 오류 문구에 섞여 나올 수 있는 API 키의 환경변수 이름 목록
SECRET_ENVS = ("ECOS_API_KEY", "DART_API_KEY", "DATA_GO_KR_KEY", "FRED_API_KEY", "FIRECRAWL_API_KEY")
# URL 안에서 키가 들어가는 파라미터 이름(값을 통째로 가림)
_KEY_PARAM = re.compile(r"(?i)(servicekey|crtfc_key|api_key|apikey|authkey|key|token)=[^&\s'\")]+")


def scrub(text: str) -> str:
    """오류 문구에서 API 키를 지운다 — 저장소가 공개라서 JSON에 키가 남으면 안 됨."""
    for name in SECRET_ENVS:
        val = os.environ.get(name)
        if not val:
            continue
        # 키 원문, URL 인코딩된 형태(+ → %2B 등) 두 가지를 모두 가림
        for form in {val, urllib.parse.quote(val, safe=""), urllib.parse.quote_plus(val)}:
            text = text.replace(form, "***")
    # 혹시 남은 '파라미터=값' 형태도 한 번 더 가림
    text = _KEY_PARAM.sub(lambda m: m.group(1) + "=***", text)
    # ECOS는 키가 주소 경로(/StatisticSearch/<키>/json/...)에 들어가므로 경로째 가림
    text = re.sub(r"(ecos\.bok\.or\.kr/api/[A-Za-z]+/)[^/\s]+", r"\1***", text)
    return text


def section(fn, errors: list, name: str):
    """섹션 하나가 실패해도 전체 수집은 계속 — 실패분은 '미확보'로 기록."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        # 키를 먼저 지운 뒤에 길이를 자른다(순서가 바뀌면 잘린 키 조각이 남을 수 있음)
        msg = scrub(f"{type(e).__name__}: {e}")
        errors.append(f"{name}: {msg[:200]}")
        return {"status": "미확보", "error": msg[:300]}


def finalize(brief: str, out: dict, errors: list) -> dict:
    ok = sum(1 for v in out.values() if isinstance(v, dict) and v.get("status") == "ok")
    meta = {
        "brief": brief,
        "date_kst": today_kst(),
        "collected_at_kst": now_kst().isoformat(timespec="seconds"),
        "run": "github-actions",
        "ok_sections": ok,
        "total_sections": len(out),
        "ok_ratio": round(ok / max(len(out), 1), 2),
        "errors": errors,
    }
    return {"meta": meta, **out}


def save(name: str, payload: dict) -> pathlib.Path:
    DATA_DIR.mkdir(exist_ok=True)
    p = DATA_DIR / name
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
