# Modelin paper 운영 실행서

## 국내주식 KIS paper

현재 자동 주문 실행기는 국내 KRX 전용이다. `workers.run_paper`는 `market=krx`만
허용하고, US와 코인은 분석·백테스트 대상으로만 유지한다. 해외 주문은 계좌·환전·
거래소 라우팅·장 운영시간 검증을 마친 뒤 별도 실행기로 추가한다.

`backend/.env`에 KIS paper 자격증명을 넣은 뒤 프로젝트 루트에서 실행한다.

```powershell
scripts\start-paper.ps1 -Market krx -IntervalSeconds 300
```

서버가 시작되면 `GET http://127.0.0.1:8000/api/health`에서 `paper_worker`가 `running`인지 확인한다.

## 미국주식 분석·준비

KIS 해외주식 paper 어댑터를 사용한다. `docs/examples/us-paper-runner.json`은 NASDAQ·NYSE·AMEX 전체 종목 유니버스를 사용하며, 종목 마스터의 거래소 코드에 따라 주문 어댑터를 선택한다. 거래소 목록을 받지 못하면 미국 전체 종목 Worker는 주문을 시작하지 않는다.

현재 기본 설정은 `PAPER_ALLOWED_MARKETS=krx`입니다. 이 설정에서는 운영 API도
국내 KRX deployment만 생성·재개할 수 있습니다. `PAPER_ALLOWED_MARKETS`에 `us`를
추가해도 현재 국내 worker는 미국 deployment를 실행하지 않습니다. 미국 자동매매는
별도 `workers.run_us_paper` 실행기에서만 다루며, 실행 전에 `PAPER_ALLOWED_MARKETS=us`와
KIS 해외계좌 설정이 필요합니다. 코인은 Paper 운영 대상에 포함하지 않습니다.

## 연결 상태 읽기 전용 점검

아래 점검은 KIS 국내·미국 계좌 잔고 조회와 FRED 거시 데이터 조회만 수행한다. 주문·취소·청산 요청은 보내지 않는다.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
py scripts/verify-integrations.py
```

개발 환경 의존성과 회귀 테스트는 다음으로 준비하고 실행한다.

```powershell
py -m pip install -r backend/requirements-dev.txt
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
py -m pytest -q
```

세 항목이 모두 `"status": "ok"`이면 현재 설정으로 읽기 연결이 확인된 것이다. KIS 자격증명이 없으면 해당 시장은 `missing_credentials`로 표시되며, FRED API 키가 없어도 공개 CSV 경로가 자동으로 사용된다.

국내 Paper 워커의 배포·계좌·세션·전체 종목 목록을 주문 없이 확인하려면 다음 사전점검을 실행한다.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
py scripts/verify-domestic-paper.py
```

결과의 `orders_submitted`는 항상 0이어야 하며, 이 명령은 주문·취소·청산 API를 호출하지 않는다.

전략 판단과 주문 수량까지 확인하되 계좌에 주문을 보내지 않으려면 다음 미리보기를 사용한다.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
py scripts/preview-domestic-paper.py
```

미리보기는 KIS 잔고·선택 종목 시세와 KRX 전체 유니버스를 읽지만 `orders_submitted`는 항상 0이다.

장 시작 전에 시세 캐시를 미리 채우려면 프로젝트 루트에서 다음 작업을 실행한다. 계좌 조회와 주문은 수행하지 않으며, 중단 후 재실행하면 이미 저장된 종목은 건너뛴다.

```powershell
py scripts/warm-market-cache.py --market krx
```

프론트 운영 화면의 실시간 진단에서 RSS는 `ok`, `degraded`, `error`로 표시된다. RSS가 실패하면 Worker는 위험 회피 상태로 전환해 신규 주문을 만들지 않는다.

KIS paper 체결 알림을 읽기 전용으로 확인하려면 다음을 실행한다. 이 listener는 체결 알림을 수신만 하며 주문을 만들지 않는다.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
py scripts/listen-kis-executions.py 005930
```

paper 주문·취소 smoke test는 명시적 확인 문자열과 종목·수량을 지정해야만 실행된다. 접수 후 즉시 취소하고 주문·잔고 상태를 출력한다.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
py scripts/kis-paper-order-smoke.py --market krx --symbol 005930 --quantity 1 --confirm I_CONFIRM_KIS_PAPER_ORDER
```

## 중지와 안전 규칙

터미널에서 `Ctrl+C`로 서버와 worker를 함께 중지한다. 코인 deployment는 runner가 거절하고, live broker는 기본 등록되지 않는다. 시작 전에 `--once` 실행으로 시장 캘린더와 데이터 공급자를 먼저 확인할 수 있다.

외부에 운영 API를 공개할 때는 `backend/.env`의 `MODEL_API_KEY`를 설정하고 요청마다 `X-Modelin-Key` 헤더를 보낸다. 비워 두면 로컬 개발용으로 인증을 생략한다.
# KIS 인증 점검

Paper 모드에서는 실전용 키가 아니라 KIS 개발자센터에서 모의투자 계좌에
발급한 `App Key`, `App Secret`, 8자리 모의계좌 번호를 함께 사용해야 한다.
`KIS_ENVIRONMENT=paper`인 상태에서 `/api/v1/diagnostics/live`를 호출했을 때
`403 Forbidden`이면 네트워크 문제보다 앱·계좌 매핑 또는 모의투자 권한 문제다.
키를 교체한 뒤 백엔드를 재시작하고 `kis_krx`와 `kis_us`가 모두 `ok`인지 확인한다.

## 시장별 Paper 실행

국내 전략을 먼저 운영할 때는 `PAPER_ALLOWED_MARKETS=krx`로 둡니다. 이 값이
기본값이며, 워커는 해외 deployment를 초기화하지 않습니다. 국내와 해외에
같은 KIS 종합계좌를 사용해도 `KIS_KRX_ACCOUNT_NO`와 `KIS_US_ACCOUNT_NO`를
비워두면 `KIS_ACCOUNT_NO`를 각각 공유합니다. `docs/examples/us-paper-runner.json`은
분석·계약 검증용이며, 미국 Paper 실행은 다음 별도 명령으로만 시작합니다.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
py -m workers.run_us_paper docs/examples/us-paper-runner.json --once
```

이 명령은 `PAPER_ALLOWED_MARKETS`에 `us`가 없으면 시작 전에 종료합니다.

주문 없이 미국 Paper 실행 전 상태를 확인하려면 다음 사전 점검을 사용합니다.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
py scripts/verify-us-paper.py
```

미국 장중 단일 종목 Paper 주문 검증은 별도 도구를 사용합니다. 주문·즉시 취소를
시도하므로, 실제 검증 시 승인한 종목과 수량만 입력합니다.

```powershell
py scripts/kis-us-paper-order-smoke.py --symbol AAPL --exchange NASD --quantity 1 --price 200 --confirm I_CONFIRM_KIS_US_PAPER_ORDER
```
### 전 종목 시세 캐시

전 종목 전략은 공개 시세 제공자로 과거 일봉을 수집하고, 성공적으로 수집된 결과를 `MARKET_DATA_CACHE_DIR`(기본값: 프로젝트 루트의 `.market-data-cache`)에 저장합니다. API와 Paper worker를 어느 폴더에서 시작해도 같은 캐시를 사용하므로 재시작 후 저장된 종목은 다시 외부 요청하지 않습니다. 빈 응답이나 오류는 캐시하지 않으므로 일시적인 장애가 정상 시세로 고정되지 않습니다.

첫 실행은 거래소 종목 수와 외부 제공자 응답 속도에 따라 시간이 걸릴 수 있습니다. 첫 수집이 끝나기 전에는 주문을 제출하지 않고 `NO_FINAL_MARKET_DATA`로 안전하게 대기합니다.

주식 Paper worker는 시장별 현지 세션 시간에도 묶여 있습니다. KRX는 한국시간
09:00–15:30, 미국은 뉴욕시간 09:30–16:00 밖에서 `MARKET_CLOSED`로 대기하며 주문을
만들지 않습니다. `backend/requirements.txt`의 `exchange-calendars`가 설치된 환경에서는
XKRX·XNYS 공식 세션과 휴장일을 사용합니다. 선택 의존성이 없는 개발 환경에서는
평일·시간대 fallback으로 동작하므로 Paper 운영 전 의존성 설치를 확인해야 합니다.
