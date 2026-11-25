"""공용 유틸 — 시간, HTTP, 페이지 수집(브라우저 우선·Firecrawl 예비), 섹션 래퍼, 저장."""
import contextlib
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
FC_CALLS = 0      # 이번 실행에서 Firecrawl을 부른 횟수(1회 = 1크레딧)
_fc_reported = 0  # finalize()가 이미 meta에 적은 횟수
_fc_dead = ""     # 크레딧 소진·키 오류가 한 번 확인되면 사유를 적어 두고, 이번 실행에서는 더 부르지 않는다


def firecrawl_enabled() -> bool:
    """NO_FIRECRAWL=1 이거나 키가 없으면 Firecrawl을 쓰지 않는다(크레딧이 바닥난 기간·점검용)."""
    return os.environ.get("NO_FIRECRAWL") != "1" and bool(os.environ.get("FIRECRAWL_API_KEY"))


def firecrawl(url: str, max_chars: int = 4000, _retry: bool = True) -> str:
    """Firecrawl scrape API. 분당 한도를 고려해 호출 간 최소 6초 간격, 429면 25초 후 1회 재시도.
    2026-11-19부터는 예비 경로 — 평소에는 fetch_md()가 브라우저로 먼저 읽고, 실패한 페이지만 여기로 온다."""
    global _last_fc, FC_CALLS, _fc_dead
    if not firecrawl_enabled():
        raise RuntimeError("Firecrawl 미사용(NO_FIRECRAWL=1 또는 키 없음)")
    if _fc_dead:
        # 2026-11-25 추가: 크레딧이 바닥난 날 페이지마다 6초씩 기다리며 같은 거절을 다시 받지 않도록 한다
        raise RuntimeError(f"Firecrawl {_fc_dead} — 이번 실행에서는 다시 부르지 않음")
    key = os.environ["FIRECRAWL_API_KEY"]
    wait = 6 - (time.time() - _last_fc)
    if wait > 0:
        time.sleep(wait)
    _last_fc = time.time()
    FC_CALLS += 1
    r = requests.post(
        "https://api.firecrawl.dev/v1/scrape",
        headers={"Authorization": f"Bearer {key}"},
        # maxAge 0 = 캐시를 쓰지 않고 지금 페이지를 새로 긁는다.
        # (기본값은 최대 2일 전 캐시를 돌려줘서 11-13 낮 수집에 11-12 목록이 들어온 사례가 있었음)
        json={"url": url, "formats": ["markdown"], "onlyMainContent": True, "maxAge": 0},
        timeout=90,
    )
    if r.status_code == 429 and _retry:
        time.sleep(25)
        return firecrawl(url, max_chars, _retry=False)
    if r.status_code in (401, 402):
        # 401 = 키 오류, 402 = 크레딧 소진. 크레딧이 나가지 않은 호출이므로 횟수에서 빼고, 남은 페이지는 부르지 않는다.
        FC_CALLS -= 1
        _fc_dead = "크레딧 소진(402)" if r.status_code == 402 else "키 오류(401)"
    r.raise_for_status()
    md = (r.json().get("data") or {}).get("markdown") or ""
    return md[:max_chars]


# ── 브라우저(Playwright)로 직접 읽기 — Firecrawl 크레딧 절감용 1순위 경로 (2026-11-19 추가) ──
# 페이지의 본문을 Firecrawl이 주던 것과 비슷한 글(제목은 '#', 링크는 '[글](주소)', 굵은 글씨는 '**')로 바꾼다.
# 메뉴·머리말·꼬리말(nav/header/footer/aside)과 그림은 뺀다.
_MD_JS = r"""
(roots) => {
  let root = null;
  for (const sel of roots) { root = document.querySelector(sel); if (root) break; }
  root = root || document.body;
  const SKIP = new Set(['SCRIPT','STYLE','NOSCRIPT','SVG','IFRAME','BUTTON','FORM','SELECT','INPUT','TEXTAREA',
                        'IMG','PICTURE','VIDEO','CANVAS','NAV','HEADER','FOOTER','ASIDE','TEMPLATE']);
  const BLOCK = new Set(['P','DIV','UL','OL','SECTION','ARTICLE','MAIN','TABLE','TBODY','THEAD','TR','DL','DT','DD',
                         'BLOCKQUOTE','FIGURE','FIGCAPTION','PRE','BR','HR']);
  const one = (t) => t.replace(/\s+/g, ' ').trim();
  const shown = (el) => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden'; };
  function walk(n, inLink) {
    if (n.nodeType === 3) return n.nodeValue.replace(/\s+/g, ' ');
    if (n.nodeType !== 1 || SKIP.has(n.tagName) || !shown(n)) return '';
    const t = n.tagName;
    let inner = '';
    for (const c of n.childNodes) inner += walk(c, inLink || t === 'A');
    if (t === 'A') {
      const txt = one(inner), href = n.href || '';
      if (!txt) return '';
      return (inLink || !/^https?:/.test(href)) ? txt : '[' + txt + '](' + href + ')';
    }
    if (t === 'STRONG' || t === 'B') { const x = one(inner); return x ? '**' + x + '**' : ''; }
    if (/^H[1-6]$/.test(t)) { const x = one(inner); return x ? '\n\n' + '#'.repeat(+t[1]) + ' ' + x + '\n\n' : ''; }
    if (t === 'LI') { const x = inner.trim(); return x ? '\n- ' + x + '\n' : ''; }
    if (t === 'TD' || t === 'TH') return ' ' + one(inner) + ' |';
    if (BLOCK.has(t)) return '\n' + inner + '\n';
    return inner;
  }
  return walk(root, false).replace(/[ \t]+\n/g, '\n').replace(/\n[ \t]+/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}
"""

# 접속 차단·확인 화면에 나오는 문구 — 이런 화면이면 읽은 것으로 치지 않는다
_BLOCK_MARKS = ("Just a moment", "Verify you are human", "Access Denied", "Access denied", "Attention Required", "Request blocked")
_ROOTS = ["main", "[role=main]", "#container", "#content", "body"]


@contextlib.contextmanager
def browser():
    """브라우저 탭 하나를 빌려 준다. 브라우저를 띄우지 못하면 None을 준다(그러면 Firecrawl 경로만 쓴다)."""
    pw = b = None
    try:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        b = pw.chromium.launch()
        page = b.new_context(locale="ko-KR", viewport={"width": 1280, "height": 1600}).new_page()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 브라우저 시작 실패 — Firecrawl 경로만 사용: {type(e).__name__}")
        page = None
    try:
        yield page
    finally:
        for closer in (getattr(b, "close", None), getattr(pw, "stop", None)):
            try:
                if closer:
                    closer()
            except Exception:  # noqa: BLE001
                pass


def render_md(page, url: str, wait_selector: str | None = None, wait_ms: int = 2500, roots=None) -> str:
    """브라우저로 페이지를 열어 본문을 글로 바꿔 돌려준다."""
    page.goto(url, timeout=40000, wait_until="domcontentloaded")
    if wait_selector:
        try:
            page.wait_for_selector(wait_selector, timeout=15000)
        except Exception:  # noqa: BLE001
            pass  # 못 찾아도 아래 검증(ok)에서 걸러진다
    page.wait_for_timeout(wait_ms)
    return page.evaluate(_MD_JS, roots or _ROOTS)


def fetch_md(page, url: str, max_chars: int, ok, **kw):
    """페이지 글과 수집 경로를 돌려준다 → (글, "playwright" 또는 "firecrawl").
    1순위: 브라우저로 직접 읽고 ok(글)로 내용이 제대로 왔는지 확인(크레딧 0).
    2순위: 직접 읽기가 실패했거나 내용이 부실하면 Firecrawl(1크레딧)."""
    why = "브라우저 없음"
    if page is not None:
        try:
            md = render_md(page, url, **kw)
            if any(m in md[:1500] for m in _BLOCK_MARKS):
                why = "차단·확인 화면"
            elif ok(md):
                return md[:max_chars], "playwright"
            else:
                why = f"내용 검증 실패(길이 {len(md)})"
            if os.environ.get("DRY_RUN") == "1":  # 점검 실행에서는 무엇이 왔는지 보여 준다
                print(f"  ! {url}: {why} | " + md[:400].replace("\n", " ⏎ "))
        except Exception as e:  # noqa: BLE001
            why = type(e).__name__
    try:
        return firecrawl(url, max_chars), "firecrawl"
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"직접 수집 실패({why}) · Firecrawl 실패({type(e).__name__}: {e})") from None


def link_count(md: str, pattern: str) -> int:
    """글 안에서 pattern에 맞는 주소를 가진 링크가 몇 개인지(중복 제외)."""
    return len(set(re.findall(r"\]\((" + pattern + r")", md)))


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


def _fc_delta() -> int:
    global _fc_reported
    n = FC_CALLS - _fc_reported
    _fc_reported = FC_CALLS
    return n


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
        "firecrawl_calls": _fc_delta(),  # 이 JSON을 만들며 쓴 Firecrawl 크레딧(0이면 전부 브라우저로 읽은 것)
    }
    return {"meta": meta, **out}


def save(name: str, payload: dict) -> pathlib.Path:
    DATA_DIR.mkdir(exist_ok=True)
    p = DATA_DIR / name
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def fetch_pages(pages: dict, ok_pattern: dict, max_chars: int = 5000, min_links: int = 8) -> dict:
    """목록 페이지 여러 곳을 읽는다. 한 곳이 안 열려도 나머지는 살리고, 전부 실패했을 때만 오류를 낸다.
    ok_pattern[이름] = 그 페이지의 기사 주소 형식 — 이런 링크가 min_links개 이상 보여야 제대로 읽은 것으로 본다."""
    out, failed = {}, []
    with browser() as page:
        for k, u in pages.items():
            try:
                md, via = fetch_md(page, u, max_chars, lambda md, k=k: link_count(md, ok_pattern[k]) >= min_links)
                out[k] = {"url": u, "via": via, "excerpt": md}
            except Exception as e:  # noqa: BLE001
                msg = scrub(f"{type(e).__name__}: {e}")[:200]
                failed.append(f"{k}: {msg}")
                out[k] = {"url": u, "via": None, "excerpt": "", "error": msg}
    if len(failed) == len(pages):
        raise RuntimeError("목록 페이지를 하나도 읽지 못함 — " + " / ".join(failed)[:260])
    return {"pages": out, "page_errors": failed}

