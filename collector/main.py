"""엔트리포인트 — 세 데일리의 JSON을 생성한다.

실행 정책:
  - 07:30 KST 크론(본 실행)과 07:50 KST 크론(재시도)이 모두 이 스크립트를 부른다.
  - 오늘자 수집본이 이미 있고 성공률(ok_ratio)이 0.7 이상이면 건너뛴다 → 재시도 크론이 자연스럽게 no-op.
  - 수동 실행(workflow_dispatch)은 FORCE=1로 항상 재수집.
  - DRY_RUN=1이면 저장하지 않고 페이지별 수집 경로(브라우저/Firecrawl)와 앞부분만 로그에 찍는다(점검용).
  - NO_FIRECRAWL=1이면 Firecrawl 예비 경로를 쓰지 않는다(크레딧이 바닥난 기간·점검용).
"""
import json
import os

from . import digital, market, retail, util

FRESH_MIN_OK = 0.7


def fresh(name: str) -> bool:
    p = util.DATA_DIR / name
    if not p.exists():
        return False
    try:
        meta = json.loads(p.read_text(encoding="utf-8")).get("meta", {})
        return meta.get("date_kst") == util.today_kst() and float(meta.get("ok_ratio", 0)) >= FRESH_MIN_OK
    except Exception:  # noqa: BLE001
        return False


def show(node, path=""):
    """수집 결과에서 페이지별 경로(via)와 글 앞부분을 로그에 찍는다."""
    if isinstance(node, dict):
        if "via" in node and "excerpt" in node:
            head = node["excerpt"][:500].replace("\n", " ⏎ ")
            print(f"  · {path}: via={node['via']} len={len(node['excerpt'])} | {head}")
        for k, v in node.items():
            if k in ("lists", "lists_via", "cross_calc", "details_skipped", "page_errors") and path.count(".") <= 1:
                if k == "lists":
                    for name, md in v.items():
                        print(f"  · {path}.lists.{name}: len={len(md)} | " + md[:500].replace("\n", " ⏎ "))
                else:
                    print(f"  · {path}.{k}: {json.dumps(v, ensure_ascii=False)[:600]}")
            else:
                show(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            show(v, f"{path}[{i}]")


def main():
    force = os.environ.get("FORCE") == "1"
    dry = os.environ.get("DRY_RUN") == "1"
    jobs = {"market.json": market.collect, "digital.json": digital.collect, "retail.json": retail.collect}
    for name, fn in jobs.items():
        if not force and not dry and fresh(name):
            print(f"[skip] {name}: 오늘자 수집본이 이미 있음")
            continue
        print(f"[run ] {name} 수집 시작")
        payload = fn()
        m = payload["meta"]
        if dry:
            show(payload)
        else:
            util.save(name, payload)
        print(
            f"[{'dry ' if dry else 'done'}] {name}: ok {m['ok_sections']}/{m['total_sections']}, "
            f"errors={len(m['errors'])}, firecrawl={m['firecrawl_calls']}회"
        )
        for e in m["errors"]:
            print(f"       - {e}")


if __name__ == "__main__":
    main()
