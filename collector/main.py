"""엔트리포인트 — 세 데일리의 JSON을 생성한다.

실행 정책:
  - 07:30 KST 크론(본 실행)과 07:50 KST 크론(재시도)이 모두 이 스크립트를 부른다.
  - 오늘자 수집본이 이미 있고 성공률(ok_ratio)이 0.7 이상이면 건너뛴다 → 재시도 크론이 자연스럽게 no-op.
  - 수동 실행(workflow_dispatch)은 FORCE=1로 항상 재수집.
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


def main():
    force = os.environ.get("FORCE") == "1"
    jobs = {"market.json": market.collect, "digital.json": digital.collect, "retail.json": retail.collect}
    for name, fn in jobs.items():
        if not force and fresh(name):
            print(f"[skip] {name}: 오늘자 수집본이 이미 있음")
            continue
        print(f"[run ] {name} 수집 시작")
        payload = fn()
        util.save(name, payload)
        m = payload["meta"]
        print(f"[done] {name}: ok {m['ok_sections']}/{m['total_sections']}, errors={len(m['errors'])}")
        for e in m["errors"]:
            print(f"       - {e}")


if __name__ == "__main__":
    main()
