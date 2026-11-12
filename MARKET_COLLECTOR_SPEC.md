# MARKET_COLLECTOR_SPEC.md — 아침 브리핑 데이터 수집기 전환 계획

작성: 2026-11-09~11-12 Cowork 대화에서 합의 · 이 문서는 프로젝트 "코딩과개발" 지식용 정리본.
새 대화에서 이 작업을 이어갈 때 이 문서 하나로 전체 맥락을 복원할 수 있게 쓴다.

## 1. 배경 — 왜 이 작업을 하는가

YJ의 아침 브리핑 3종은 현재 각각 PC(맥북)/Cloud(클라우드 대체) **이중 예약 작업**으로 운영 중:

| 브리핑 | PC판 (기본) | Cloud판 (대체) |
|---|---|---|
| 데일리 마켓 브리프 | trig_012Nm7h6Tz5GTyx9xrqqyGsZ · 매일 08:00 (구명 "Morning market briefing" → 11/9에 "데일리 마켓 브리프-PC"로 개명) | trig_01KWpcUuYFx1DMN38kehXckz · 매일 08:25 |
| 데일리 디지털 브리프(STO) | trig_012rioAe2BSRhgGRngKH8eyc · 평일 08:10 | trig_01TVueRL38RGKA6Kyy2afNFJ · 평일 08:35 |
| 리테일 상품 데일리 | trig_01Uo1CPvfweeZCR8nV6Cdw65 · 평일 08:10 | trig_015QP1hf7yvgdhozjo9Q9q7N · 평일 08:40 |

이원화의 원인은 AI가 아니라 **데이터 수집 경로**: KRX·ECOS·DART·Firecrawl 래퍼 MCP와 내장 브라우저(한경)가
맥북 로컬에 붙어 있어, 맥북이 꺼진 날은 Cloud판이 WebSearch/WebFetch만으로 "간이판"을 만든다.
Cloud판은 PC판의 당일 실행 성공 여부를 trigger id로 확인해 성공 시 스킵한다.

## 2. 검토한 선택지와 결정

- ① 데이터 커넥터만 원격 MCP로 호스팅(실시간 제공) — AI는 예약 작업 그대로, API 비용 0
- ② 완전 외부 서버(수집+생성, Claude Code 구독 OAuth) — `claude setup-token`으로 API 과금 없이 가능하나,
  OAuth 토큰을 Agent SDK 등에 꽂는 우회는 약관상 차단 강화 추세 + 토큰 만료로 무인 자동화 끊김 이슈
- ③ **서버는 AI 없이 수집만**(JSON 사전 적재) — 브리핑 생성은 지금의 구독 기반 예약 작업이 수행

**결정: ③ 채택.** 근거: 수집 항목이 소스 맵으로 고정된 루틴이라 사전 적재와 궁합이 좋고, MCP 규격 없이
평범한 스크립트면 되고, AI API 비용 0. ①/③의 차이는 "실시간 MCP 제공 vs JSON 사전 적재"일 뿐 브라우저
유무가 아님(서버에 Playwright를 두면 JS 페이지도 수집 가능).

호스팅: 전용 서버 없음 → **GitHub Actions**(무료, 하루 ~8분, 서버 관리 불요). 저장소는 **Public**
(비공개면 raw URL을 예약 작업이 못 읽음; 키는 Secrets라 안전). 대안은 Oracle Free/Hetzner VPS.

YJ 확정 사항: 수집 **07:30 KST 시작**, **실패 시 재시도**, 브리핑 시각 **08:10으로 통합**, **세 데일리 모두 한 번에** 적용,
GitHub 계정 있음(절차 안내 필요).

## 3. 만들어 둔 것 (2026-11-09 전달 완료)

저장소 이름: `market-collector` · 전달물: zip(대화 첨부) + 맥북 `~/market-collector/` 폴더.
워크플로 파일만 보호 경로 문제로 맥북에는 `collect.yml (깃허브에서는….yml)` 이름으로 저장됨 —
GitHub에서는 반드시 `.github/workflows/collect.yml` 경로에 넣는다.

구성:
- `.github/workflows/collect.yml` — cron 22:30 UTC(=07:30 KST) 본 실행 + 22:50 UTC(07:50) 재시도
  (오늘자 수집본의 ok_ratio ≥ 0.7이면 스킵) + workflow_dispatch(수동, FORCE=1) → `data/` 커밋·푸시
- `collector/util.py` — KST 시간, HTTP, Firecrawl(6초 간격·429 시 25초 후 1회 재시도), 섹션 래퍼(실패="미확보"), meta 생성
- `collector/market.py` — **market.json**: FRED API 9시리즈 · ECOS 817Y002 5종(국고3/10/30y·회사채AA-·CD91)
  · KRX 공공데이터포털(코스피·코스닥 + 005930/000660/042700) · OpenDART 3사(직전 거래일, 월→금)
  · TE 7페이지(Firecrawl — us10y/us30y/gold/dxy/usdkrw/usdjpy/usdbrl + 재정환율 자동 산출:
  원/엔=USDKRW÷USDJPY×100, 원/헤알=USDKRW÷USDBRL) · 네이버 리서치 목록 4 + 상세 상위 6건(PDF URL 추출)
  · 한경 컨센서스·종목페이지 3(Playwright, 로그인 불필요 영역만)
- `collector/digital.py` — **digital.json**(보조): 토큰포스트 브리핑·최신 목록, 금융위 보도자료 목록
- `collector/retail.py` — **retail.json**(보조): 한경 economy/1212·1213, 중앙 money/finance 목록
- JSON 공통 meta: `date_kst` · `collected_at_kst` · `ok_ratio` · `errors[]` — 브리핑 작업의 신선도 판정용
- README.md — GitHub 초심자용 5단계 설치 가이드(저장소 생성→업로드→Secrets→수동 실행→raw URL)

필요 Secrets 5개(이름 고정): `ECOS_API_KEY` · `DART_API_KEY` · `DATA_GO_KR_KEY`(금융위 지수시세정보+주식시세정보
활용신청 필요) · `FRED_API_KEY`(신규 무료 발급) · `FIRECRAWL_API_KEY`. 키 값은 Claude에게 보내지 않고 Secrets에만.

검증된 사실: 클라우드 예약 작업 샌드박스의 셸에서 `raw.githubusercontent.com` **접근 가능(200) 확인** —
즉 예약 작업이 `curl`로 JSON을 수치 손실 없이 읽을 수 있음(api.github.com·gist는 403 차단, WebFetch는 보조 경로).
코드·YAML·환율 파서는 문법/셀프테스트 통과, 실제 API 응답은 첫 실행에서 검증 필요(디버깅 1회 왕복 예상).

설계 원칙(유지할 것):
- 차단 도메인(yna·mk·biz.chosun·einfomax) 원문은 **수집기로도 대체하지 않음**(Claude 웹 도구 차단 우회 금지) —
  해당 매체는 맥북 Chrome이 연결된 날에만. 한경 로그인 전용 리포트 PDF 원문도 미수집(목록·목표가·기사 교차로 대체)
- 뉴스(마감 기사·정산가·하우스 코멘트·진원지 심층)는 계속 브리핑 작업의 WebSearch가 담당 — JSON은 정형 수치 담당
- 품질 구조: 평상시=현 PC판 수준, 수집 실패일=현 Cloud 간이판 수준(JSON이 오늘자가 아니면 직접 수집으로 폴백)
- Firecrawl 소모 ~월 700크레딧 · Bigdata.com은 크레딧 소진으로 미사용

## 4. 남은 단계 (이 순서대로)

1. **[YJ]** README 5단계 수행: Public 저장소 생성 → 파일 업로드(.github 경로 주의) → Secrets 5개 →
   Actions에서 Run workflow 1회 → `data/market.json` 생성 확인, raw URL 확보
2. **[Claude]** 첫 실행 로그/JSON 검수, 실패 모듈 수정(1회 왕복 예상)
3. **[Claude]** 예약 작업 개정: 세 브리핑 프롬프트를 "JSON 우선(curl raw URL, 신선도 meta 확인) + WebSearch 보완,
   미신선 시 간이판 폴백" 구조로 재작성 → PC/Cloud 6개를 **08:10 클라우드 단일 작업 3개로 통합**
   (Cloud 트리거를 update_trigger로 개정하는 쪽이 간단 — PC 트리거는 기기 결합이라 프롬프트 변경에 기기 승인 필요)
4. 수일 모니터링 후 PC판·구 Cloud판 비활성/정리. 대시보드(https://claude.ai/artifact/Jh7LBpG5HugSPn1HuYowMj)
  연결 상태 칩 문구도 새 구조로 갱신

## 5. 새 대화에서 시작하는 법

"MARKET_COLLECTOR_SPEC.md 읽고 수집기 전환 작업 이어서 진행" + 현재 상태(저장소 만들었는지, 첫 실행 결과,
raw URL)를 알려주면 3~4단계부터 진행 가능.
