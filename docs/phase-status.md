# Modelin 단계별 진행 상태

기준일: 2026-09-12

## 1. 코인 보류

코인 자동매매 주문은 비활성화했다. 코인 시세와 백테스트 코드는 남겨 두되, 주문 API는 `409`로 거절한다.

## 2. 국내주식 모의매매

KIS 모의 API의 토큰·잔고·현금주문·주문조회·취소 요청을 연결했다. API 키는 `backend/.env`에만 두며 저장소에는 올리지 않는다.

## 3. 자동 실행 검증

전략 신호, 주문계획, 매도 우선 처리, 현금 버퍼, 리스크 차단, 중복 실행 잠금, 재시작 복구를 백엔드에 반영했다. 실행 워커는 paper 모드만 허용한다.

## 4. 백테스트 비교

백테스트와 실행 워커가 동일한 전략 런타임 계약을 사용한다. 수수료·세금·슬리피지·다음 봉 시가 체결·거래량 제한을 반영한다.

## 5. 미국주식 연결

미국 시세 프로바이더와 시장 캘린더 구조는 준비되어 있다. 주문 브로커는 업체와 계좌가 정해지지 않아 `DisabledLiveBroker`로 차단한다. 업체가 정해지면 같은 Broker Protocol에 어댑터를 추가한다.

## 6. 운영 화면

계좌·배포·잔고·주문·이벤트·실행 상태를 조회하는 API와 거래 패널을 연결했다. 명령에는 멱등키와 revision 검사를 적용한다.

## 7. 실거래 전 안전장치

live 어댑터는 기본 등록하지 않는다. paper/live 모드를 계좌 생성 시 고정하고, 지원되지 않는 live 주문·잔고·이벤트 요청은 차단한다. 실거래 전환은 별도 브로커 검증 후에만 가능하다.

## 남은 외부 검증

- KIS 모의계좌에서 사용자가 승인한 종목·수량으로 주문·취소 1회 검증
- KIS 해외주식 주문·잔고 어댑터 구현과 모의계좌 검증 필요
- KIS 체결 웹소켓 운영 consumer(REST 재대사 polling은 구현됨)
- 장기간 paper 운용 후 실거래 전환 검토

실거래 gate는 명시적 승인 문자열, live capability, 배포 확인, 주문 금액 한도를 모두 요구하며 기본값은 차단이다.

GitHub Actions CI가 master push와 pull request마다 백엔드 테스트·컴파일과 프론트엔드 production build를 수행한다.

## 적응형 전략 방향

`backend/core/regime_router.py`는 가격 추세·변동성에 환율 충격과 외부 위험 점수를 결합해 `TREND_UP`, `TREND_UP_HIGH_VOL`, `TREND_DOWN`, `RISK_OFF`를 판정한다. 전략에 `adaptive: true`를 지정하면 라우터가 국면에 따라 모멘텀 전략을 활성화하거나 주문을 차단한다. 뉴스 모델은 향후 `context.risk_off`와 같은 검증된 수치 입력으로만 연결하며, 뉴스 원문이 주문을 직접 만들 수 없도록 한다.

`backend/core/market_context.py`에는 뉴스 제목을 이벤트 유형과 영향도·신뢰도로 변환하는 기본 엔진과 환율·금리·뉴스를 제한된 수치 컨텍스트로 합치는 계층을 추가했다. 실제 뉴스 공급자는 이 경계 뒤에 연결하며, 공급자 장애나 낮은 신뢰도에서는 위험을 낮추는 방향으로만 동작한다.

`backend/adapters/market_data/news_feed.py`는 설정된 RSS 피드를 실행 주기마다 읽고, 모든 피드가 실패하면 해당 컨텍스트를 `risk_off=1.0`으로 만들어 주문을 보수적으로 차단한다.

공식 이벤트 출처는 `backend/adapters/market_data/official_sources.py`에서 OpenDART와 SEC EDGAR를 별도 수집한다. DART는 `OPENDART_API_KEY`와 deployment의 `corp_codes`, SEC는 `SEC_USER_AGENT`와 `SEC_CIKS`가 설정된 경우에만 실행되며, 수집 이벤트에는 출처·접수일·원문 URL·공시 식별자를 보존한다.

`backend/core/strategy_comparator.py`는 같은 가격 표본과 거래비용을 여러 전략에 동시에 적용하고, 수익률만이 아니라 CAGR·샤프·최대낙폭을 반영해 순위를 만든다. 최고 순위 결과를 자동으로 실거래에 투입하지 않고 paper 후보로만 사용한다.
