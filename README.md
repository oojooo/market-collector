# market-collector — 아침 브리핑 데이터 수집기

매일 **07:30 KST**에 GitHub Actions가 자동 실행되어, 세 데일리 브리핑이 쓸 데이터를
`data/market.json` · `data/digital.json` · `data/retail.json`으로 저장합니다.
07:50에 재시도 크론이 한 번 더 돌며, 본 실행이 성공했으면 자동으로 건너뜁니다.
맥북 전원과 무관하게 돌아가는 것이 목적입니다.

수집 범위: FRED(미 지수·금리) · 한국은행 ECOS(국고채·회사채·CD) · KRX 공공데이터포털(지수·관심 3사)
· OpenDART(관심 3사 공시) · TradingEconomics 7페이지(당일 호가·재정환율, Firecrawl)
· 네이버페이 증권 리서치 목록+상세(Firecrawl) · 한경 컨센서스·종목페이지(Playwright, 로그인 불필요 영역).
뉴스(마감 기사·정산가·하우스 코멘트·진원지 심층)는 지금처럼 브리핑 작업의 WebSearch가 담당합니다.
연합뉴스·매일경제·조선비즈 등 Claude 웹 도구 차단 도메인은 이 수집기로도 수집하지 않습니다(우회 금지 원칙).

---

## 설치 (한 번만, 약 30~40분)

### 1단계 — 저장소 만들기
1. github.com 로그인 → 우상단 **+** → **New repository**
2. Repository name: `market-collector`
3. **Public** 선택 (중요: 비공개로 하면 예약 작업이 JSON을 읽지 못합니다.
   코드와 공개 시장 데이터만 올라가고, API 키는 Secrets에 들어가므로 공개돼도 안전합니다)
4. "Add a README file" 체크 → **Create repository**

### 2단계 — 파일 올리기
전달받은 `market-collector.zip`의 압축을 풀고:
1. 저장소 페이지에서 **Add file → Upload files**
2. 압축 푼 폴더 안의 내용물 전부(`collector` 폴더, `data` 폴더, `requirements.txt`, `README.md`)를
   창으로 **드래그** → 아래 **Commit changes**
3. `.github` 폴더는 숨김 폴더라 드래그에서 빠질 수 있습니다. 빠졌다면:
   **Add file → Create new file** → 파일 이름 칸에 `.github/workflows/collect.yml` 이라고 치면
   폴더가 자동으로 만들어집니다 → zip 안의 `collect.yml` 내용을 통째로 붙여넣기 → Commit changes

### 3단계 — API 키 5개를 Secrets에 등록
저장소에서 **Settings → Secrets and variables → Actions → New repository secret**
아래 5개를 하나씩 등록합니다. 이름은 정확히 이대로:

| Name | 내용 | 발급/확인처 |
|---|---|---|
| `ECOS_API_KEY` | 한국은행 ECOS 키 | 맥북 MCP에 이미 발급돼 있음 · 신규는 ecos.bok.or.kr/api (무료) |
| `DART_API_KEY` | OpenDART 키 | 맥북 MCP에 이미 있음 · 신규는 opendart.fss.or.kr (무료) |
| `DATA_GO_KR_KEY` | 공공데이터포털 일반 인증키(Decoding) | 맥북 MCP에 이미 있음 · data.go.kr → "금융위원회_지수시세정보"와 "금융위원회_주식시세정보" 두 API에 활용신청 돼 있어야 함 |
| `FRED_API_KEY` | FRED API 키 | fred.stlouisfed.org → My Account → API Keys (무료, 즉시 발급) |
| `FIRECRAWL_API_KEY` | Firecrawl 키 | firecrawl.dev 대시보드 (기존 계정 키 재사용) |

> 키 값은 제(Claude)게 보내지 마시고 GitHub Secrets에만 넣어 주세요.

### 4단계 — 첫 실행(수동 테스트)
1. 저장소 상단 **Actions** 탭 → 안내가 나오면 "I understand… enable them" 클릭
2. 왼쪽 **collect-daily-data** → 오른쪽 **Run workflow** 버튼 → 초록 **Run workflow**
3. 5~10분 뒤 실행이 ✅ 초록색으로 끝나면 성공. ❌ 빨간색이면 실행 로그 화면을 캡처해서 Claude에게 보여 주세요.

### 5단계 — 결과 확인과 URL
성공하면 저장소에 `data/market.json` 등 3개 파일이 생깁니다.
`data/market.json` 클릭 → 우측 **Raw** 버튼 → 주소창의 URL이 예약 작업이 읽을 주소입니다.
형태: `https://raw.githubusercontent.com/<계정명>/market-collector/main/data/market.json`

**이 URL을 Claude에게 알려 주면**, 세 예약 작업의 프롬프트를 "JSON 우선 + WebSearch 보완" 구조로
개정하고 PC/Cloud 이중 작업을 08:10 단일 작업으로 합치는 다음 단계를 진행합니다.

---

## 운영 메모
- **비용**: GitHub Actions 무료 한도 내(일 ~8분). Firecrawl은 하루 약 20~25크레딧(월 ~700) 소모.
- **신선도 판정**: 각 JSON의 `meta.date_kst`·`meta.collected_at_kst`로 브리핑 작업이 오늘자인지 확인하고,
  아니면 간이판(직접 수집)으로 동작합니다. `meta.errors`에 실패 섹션이 기록되고 해당 값은 "미확보" 처리됩니다.
- **스케줄 지연**: GitHub 크론은 혼잡 시 10~20분 밀릴 수 있어 07:30 + 07:50 이중 크론으로 보완합니다.
- **한계**: 한경 로그인 전용 리포트 PDF 원문은 수집하지 않습니다(목록·목표가·기사 교차로 대체).
- **페이지 구조 변경으로 특정 섹션이 계속 실패하면**: Actions 로그의 오류 메시지를 Claude에게 보여 주면 해당 모듈을 고쳐 드립니다.
