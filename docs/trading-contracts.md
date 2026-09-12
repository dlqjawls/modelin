# 자동 운용 데이터·API 계약 v1

작성: 2026-09-12 · 구현 예정 계약. 현재 서버에 아래 API가 구현되어 있다는 의미가 아니다.

상위 문서: [자동 운용 상세 설계](trading-system-design.md)

## 1. 공통 타입과 검증

- 식별자는 UUID. 외부 심볼은 instrument_id에 대한 매핑 값이며 계좌·거래 장소 없이 단독 식별자로 사용하지 않는다.
- Money/Quantity/가격/비율은 API에서 10진 문자열, 원장 계산에서 Decimal. NaN, Infinity, 지수 표기의 비정상 값은 거절한다.
- 시각은 ISO 8601 UTC(Z), 내부 timezone-aware. 날짜만 필요한 session_date는 별도 DATE.
- schema_version은 정수 1. 알 수 없는 버전·필드·enum은 422로 거절한다.
- 생성에는 Idempotency-Key를 사용한다. 범위는 owner_id+endpoint+key이며 정규화한 요청 해시를 저장한다. 같은 키·같은 요청은 원 응답, 같은 키·다른 요청은 409다.
- mode는 계좌와 deployment 생성 시 결정하며 변경 불가. 비밀키 존재 여부로 live 모드가 자동 선택되지 않는다.
- 모든 계좌 관련 API는 소유권을 확인한다. account_id와 deployment_id가 연결된 계좌가 다르면 거절한다.
- 위험 한도와 전략값은 예시 JSON으로 실거래 활성화할 수 없다. 활성화는 mode 일치·능력 검사·데이터 준비·최근 대사·필수 한도 검증이 필요하다.

## 2. 도메인 포트

아래는 Python 구현의 의미 계약이다. 실제 타입은 domain/models.py 등에 정의한다.

```python
class Strategy:
    def evaluate(self, context: DecisionContext) -> Decision: ...

class MarketData:
    async def snapshot(self, request: SnapshotRequest) -> DataSnapshot: ...

class Broker:
    async def capabilities(self, account_id: UUID) -> BrokerCapabilities: ...
    async def account_snapshot(self, account_id: UUID) -> AccountSnapshot: ...
    async def submit(self, request: BrokerOrderRequest) -> SubmitOutcome: ...
    async def cancel(self, order_ref: OrderRef) -> CancelOutcome: ...
    async def lookup_order(self, query: OrderQuery) -> LookupOutcome: ...
    async def order_events(self, request: EventPageRequest) -> EventPage: ...

class TradingRepository:
    async def commit_plan(self, plan: PlanCommit) -> PlanReceipt: ...
    async def apply_broker_event(self, event: BrokerEvent) -> ApplyReceipt: ...
    async def apply_control(self, control: ControlCommand) -> ControlReceipt: ...
```

Strategy는 순수 판단으로 동일 context에 동일 결과를 내야 한다. context는 clock 시각, 불변 데이터 snapshot, 실제 보유·목표 상태, 전략 설정을 포함한다. 직접 현재 시각을 읽거나 네트워크를 호출하지 않는다.

SubmitOutcome = ACKNOWLEDGED | REJECTED | UNKNOWN. 네트워크 오류를 REJECTED로 변환하지 않는다. LookupOutcome = FOUND | CONFIRMED_ABSENT | INDETERMINATE. 단순 조회 실패나 일시적 '목록에 없음'을 CONFIRMED_ABSENT로 취급하지 않는다.

BrokerCapabilities에는 시장/상품, 지원 주문 종류, 수량·총액 입력 지원, 사용자 주문 ID와 조회 지원, 세션, 취소·이벤트·모의 지원 여부를 둔다. 지원되지 않는 주문을 가장 비슷한 다른 주문으로 조용히 변환하지 않는다.

이벤트 페이지에는 cursor, next_cursor, 관측 구간, broker_event_id를 둔다. 중단 후 겹치는 구간을 재조회하여 누락을 줄이고 중복은 DB에서 차단한다. broker_event_id가 없다면 어댑터가 제공하는 안정 식별 방법을 검증해야 하며, 단순 가격·수량 조합으로 서로 다른 체결을 합치면 안 된다.

## 3. 핵심 모델

| 모델 | 필수 필드 | 제약 |
| --- | --- | --- |
| Instrument | id, market, venue, asset_type, symbol, quote_currency, calendar_id | 심볼 변경은 기간별 alias로 보존 |
| InstrumentRule | instrument_id, effective_from/to, qty_step, price_rule, min_notional, source | 시점별 규칙. 코드에 시장 상수 산재 금지 |
| Bar | instrument_id, timeframe, bar_start/end, session_date, available_at, is_final, OHLCV, source, revision | end>start, volume>=0, high>=open/close>=low, 양의 가격 |
| StrategyVersion | strategy_id, version, schema_version, spec, content_hash, created_at | 저장 뒤 수정 불가 |
| Deployment | owner_id, account_id, strategy_version_id, mode, allocation_currency, allocation_amount, risk_policy, desired_state, observed_state, pause_epoch | 계좌 모드·통화 계약 일치, 활성 계좌 중복 배포 금지 |
| Decision | run_id, kind, target_weights, reason_codes, decision_at, valid_until, snapshot_id, proposed_state | TARGET만 가중치 포함. 합<=1, 비중>=0 |
| OrderIntent | run_id, revision, account_id, instrument_id, side, qty 또는 quote_amount, price_limit, expires_at, pause_epoch, reason | 둘 중 정확히 하나의 크기 입력, 양수 |
| Order | intent_id, broker_order_id, client_order_id, lifecycle, resolution, cancel_state, submitted_at | 외부 ID 범위는 계좌별, 실제 체결로 잔량 계산 |
| Fill | account_id, order_id, external_fill_id, qty, price, fee_amount/currency, executed_at, received_at | qty/price>0, 이벤트별 1회 반영 |
| Cash | account_id, currency, total, local_reserved, broker_available, snapshot_at | 가용액은 예약 중복 차감 없이 계산 |
| Position | account_id, instrument_id, quantity, cost_basis, revision | v1 숏 불가, 원장 기반 projection |

가격·수량 저장 기본안은 NUMERIC(38,18), 거래 장소의 지원 정밀도가 이를 초과하면 해당 상품을 거절하고 저장 계약을 확장한다. 무조건 8자리로 잘라 기록하지 않는다. 통화별 최소 단위 반올림은 체결 원본 수수료를 보존한 뒤 보고 단계에 적용한다.

v1 deployment는 단일 거래 통화로 운용한다. 멀티통화 계좌는 허용하되 deployment의 주문 예산과 다른 통화를 자동 소비하지 않는다. 외부 fee_currency가 다르면 해당 통화 원장에도 명시적 이벤트로 반영한다.

## 4. 테이블 관계와 무결성

기존 schema.sql 테이블은 보존하고 v2_ 접두 신규 테이블로 전환한다. 실행 가능한 PostgreSQL migration은 `backend/migrations/001_trading_foundation.sql`에 있으며, 로컬 검증은 SQLite repository를 사용한다.

| 테이블 | 핵심 관계·제약 |
| --- | --- |
| v2_instruments, v2_instrument_aliases, v2_instrument_rules | 시장·거래 장소별 심볼 유효기간 중복 금지. 규칙 기간 중복 금지 |
| v2_data_snapshots, v2_bars, v2_fundamental_versions | bar unique(instrument,timeframe,start,source,revision). snapshot 구성 버전 고정 |
| v2_strategy_versions | unique(strategy_id,version), content_hash 저장 |
| v2_accounts | owner_id 필수, mode, broker, external_account_ref, credential_ref. 인증정보 본문 제외 |
| v2_deployments | account_id/owner_id 일치 복합 FK. 활성/대사/중지 상태 포함 계좌당 deployment 한 개를 부분 유니크로 제약 |
| v2_strategy_runs | unique(deployment_id,schedule_key). 같은 일정의 재시도는 같은 run, attempt 증가 |
| v2_order_intents | unique(run_id,revision,instrument_id,side,slice_no). expires_at와 기준 snapshot 기록 |
| v2_orders | unique(account_id,client_order_id), broker_order_id 존재 시 계좌 내 unique. intent와 account 일치 복합 FK |
| v2_order_events, v2_fills | unique(account_id,external_event_id), unique(account_id,external_fill_id). 실제 주문 계좌 일치 검증 |
| v2_journals, v2_postings | 이벤트→journal 1개. 통화/자산 단위별 차변·대변 합 일치 검증 |
| v2_cash, v2_positions, v2_reservations | 계좌+통화/상품 unique. 예약은 주문별로 하나, 중복 해제 금지 |
| v2_outbox | unique(event_key), 상태/attempt/next_attempt_at/lease. 같은 intent가 재전송 가능인지 확인 후 발송 |
| v2_account_leases | account_id PK, lease_owner, lease_until, fencing_token. DB 시계 기반 |
| v2_reconciliations, v2_risk_events, v2_heartbeats | 계좌와 run 연결, 차이·관측 시각·해소 근거 |
| v2_api_requests, v2_control_commands | API 멱등키/요청 해시, 명령 상태/결과/기대 deployment revision |
| v2_backtest_jobs, v2_backtest_results | immutable config/data versions, 실제 기간, 한계, ledger digest |

활성 deployment는 PAUSED 상태라도 계좌 소유를 유지한다. 교체 시 미체결 없음·보유 귀속 처리·잔고 대사를 마친 뒤 이전 deployment를 ARCHIVED로 바꾸어 락을 해제한다. 이전 기록을 cascade delete하지 않는다.

계좌·전략·주문 관계에 owner_id와 account_id를 포함한 FK/서버 검증을 적용해 서로 다른 사용자 계좌 연결을 차단한다. 원장·이벤트는 앱 사용자가 수정/삭제할 수 없게 하고 정정은 반대 분개와 새 이벤트로 남긴다. RLS는 조회 소유권, 원장 쓰기는 제한된 서버 역할/DB 함수로 통제한다.

v1의 원장 저장은 서버 전용 PostgreSQL 직접 연결의 단일 트랜잭션으로 예약·주문·원장을 함께 갱신한다. Supabase는 PostgreSQL 호스팅·인증을 활용할 수 있으며, 기존 클라이언트의 여러 독립 REST 호출을 하나의 트랜잭션으로 간주하지 않는다. 직접 연결 가능한 환경이 마련되기 전에는 PostgreSQL 모의 통합 테스트까지 진행하고 REST 다중 호출로 대체하지 않는다.

## 5. 원장과 예약 처리

예: 현금 1,000, 100원짜리 9개, 수수료 9의 가상 매수.

1. 발송 전 909를 local_pending 예약. total_cash=1,000은 유지하고 새 주문 예산만 줄인다.
2. 브로커 접수 확인 후 예약을 broker_managed로 전환한다. broker_available에 이미 반영된 잠금을 다시 차감하지 않는다.
3. 전량 체결 시 cash=-909, position=+9, acquisition_cost=+909를 동일 journal로 반영하고 잔여 예약을 해제한다.
4. 현금 원장에서는 투자 원가 900·수수료 9를 상대 계정으로 기록하고, 자산 수량 원장에서는 거래 상대 계정과 9개 이동을 기록한다. 원가 projection은 매수 수수료 포함 909다.
5. 매도 실현손익은 수령액-매도 비용-FIFO 배분 원가. 평가손익은 시가평가-남은 원가다.

가용 주문 예산 = min(동일 관측 기준으로 조정한 broker_available, 로컬 경제적 현금 한도, deployment 남은 예산). local_pending만 추가 차감하고 broker_managed 예약은 broker_available과 중복 차감하지 않는다. 스냅샷이 주문보다 오래되거나 반영 여부가 불명확하면 보수적으로 보류/추가 조회한다.

부분체결은 각 fill마다 원가·현금·수량을 반영하고 나머지 수량의 예약만 유지한다. 취소 요청 시점에는 예약을 풀지 않는다. 취소 확정 후에도 늦게 전달된 체결이 있을 수 있으므로 최종 주문 누적 체결과 fill 합계를 대조한다.

브로커가 허용 범위를 벗어난 가격·수수료로 이미 체결했다면 실제 사실을 원장에 반영해야 한다. 계획 불변식 위반을 이유로 fill을 버리지 않는다. 차이를 risk event로 기록하고 계좌를 ATTENTION으로 전환한다. 이 경우 가용현금이 음수로 관측될 수 있으므로 projection 제약으로 사실 기록을 막지 않는다. '음수 예산 주문 금지'는 주문 계획 검증이다.

## 6. 주문 상태

단일 enum에 모든 의미를 넣지 않고 세 축을 둔다.

- lifecycle: CREATED, SUBMITTING, OPEN, PARTIALLY_FILLED, FILLED, REJECTED, CANCELED, EXPIRED.
- resolution: KNOWN, UNKNOWN. UNKNOWN은 lifecycle의 마지막 확인 상태를 보존한다.
- cancel_state: NONE, REQUESTED, CONFIRMED, REJECTED.

| 사건 | 상태/처리 |
| --- | --- |
| DB에 의도·예약 생성 | CREATED, outbox 대기 |
| 발송 작업 확보·검사 통과 | SUBMITTING, attempt 기록 후 외부 호출 |
| 접수 응답 | OPEN 또는 응답의 실제 체결 상태, broker ID 연결 |
| 명시적 거부 | REJECTED, 미사용 예약 해제 |
| 전송 후 응답 불명 | resolution=UNKNOWN. 자동 신규 발송 차단, 조회 작업 생성 |
| 부분체결 | fill 중복 검사 → journal 반영 → PARTIALLY_FILLED |
| 전량체결 | FILLED, 남은 예약 해제 |
| 취소 요청 | cancel_state=REQUESTED, lifecycle 보존 |
| 취소 도중 전량체결 | FILLED. 취소 성공으로 덮어쓰지 않음 |
| 취소 확정 | CANCELED + CONFIRMED, 최종 fills 대조 후 잔여 예약 해제 |
| 늦은 체결/정정 | 실제 누적 수량과 상태 재대사. 필요한 journal을 보정하고 과거 이벤트 보존 |

REJECTED/CANCELED 이후 재주문은 새 intent revision과 새 client_order_id를 사용한다. UNKNOWN을 단순 실패로 간주해 새 ID로 재전송하지 않는다. 외부에서 미접수가 확정되고 기존 ID 재사용 정책까지 확인된 경우에만 명시적 recovery decision을 기록해 재발송한다.

## 7. 원자성·리스·장애 창

계좌 리스는 만료 시간과 증가하는 fencing_token을 가진다. 모든 계획 commit은 최신 token, account revision, pause_epoch를 검증한다. outbox는 짧은 트랜잭션에서 claim하며 외부 HTTP 호출 동안 DB row lock을 오래 잡지 않는다.

리스만으로 외부 주문 중복을 완전히 막을 수는 없다. 이전 워커가 중단되었다가 살아나 이미 시작한 호출을 완료할 수 있다. 따라서 새 워커는 SUBMITTING/UNKNOWN을 조회 복구하기 전 같은 intent를 보내지 않는다. broker client_order_id 지원 여부에 맞춰 조회하고, 검증할 수 없으면 ATTENTION을 유지한다.

| 장애 창 | 복구 |
| --- | --- |
| plan commit 이전 종료 | 미생성. 같은 run_id로 재판단 가능 |
| commit 이후 발송 전 종료 | outbox 재획득 후 유효기간·epoch·리스 재검사 |
| SUBMITTING 기록 후 외부 호출 전후 종료 | 실제 전송 여부 불명. 무조건 주문 조회부터 |
| 접수 성공 후 DB 반영 전 종료 | client_order_id/브로커 이력으로 기존 주문 연결 |
| fill 수신 후 journal commit 전 종료 | 이벤트 재조회. journal 유니크로 1회 적용 |
| journal commit 후 cursor 저장 전 종료 | 동일 트랜잭션으로 처리하거나 중복 재조회 후 건너뜀 |
| pause와 send 경쟁 | 새 epoch는 미전송 작업 차단. 전송 중 주문은 결과 추적하고 선택한 취소 정책 적용 |

## 8. API 계약

기존 /api 경로는 전환 기간 유지, 새 계약은 /api/v1로 분리한다.

| 메서드·경로 | 역할 | 정상 응답 |
| --- | --- | --- |
| POST /accounts/paper | 가상 계좌·초기자금 journal 생성 | 201 Account |
| GET /accounts | 소유 계좌 목록·mode·통화 | 200 목록 |
| GET /accounts/{id}/snapshot | 현금·예약·포지션·시세/FX 시각 | 200 Snapshot |
| GET /capabilities?account_id=… | 시장·주기·전략·주문 지원 범위 | 200 Capabilities |
| POST /strategies | 전략 초안 및 첫 불변 버전 | 201 StrategyVersion |
| POST /strategies/{id}/versions | 파라미터 검증 후 새 버전 생성 | 201 StrategyVersion |
| POST /backtests | 불변 설정과 데이터 요청으로 작업 생성 | 202 Job |
| GET /backtests/{id} | 대기/진행/실패/완료 및 결과 링크 | 200 Job |
| POST /deployments | account+strategy_version+allocation+risk 연결, 초기 DRAFT | 201 Deployment |
| POST /deployments/{id}/commands | START/PAUSE/CANCEL_OPEN/LIQUIDATE/RESUME/ARCHIVE | 202 Command |
| GET /deployments/{id} | desired/observed 상태, 다음 일정, 진단 | 200 Deployment |
| GET /commands/{id} | 제어 명령의 실제 적용 상태 | 200 Command |
| GET /deployments/{id}/runs | 판단 근거와 목표·데이터 버전 | 200 페이지 |
| GET /accounts/{id}/orders | 주문·부분체결·복구 상태 | 200 페이지 |
| GET /orders/{id} | 주문 의도/실제값/체결/이벤트 | 200 OrderDetail |
| POST /orders/{id}/cancel | 동일 위험·원장 경로로 취소 명령 | 202 Command |
| GET /accounts/{id}/events | 운영 이벤트 cursor polling | 200 페이지 |
| GET /health/live | API 프로세스 생존 | 200 |
| GET /health/ready | DB/필수 의존성 준비 | 200 또는 503 |

경로 표는 /api/v1 이후의 경로다. 워커와 브로커 건강 상태는 deployment 응답에서 따로 표시하며 API 프로세스가 살아 있다고 거래 정상으로 표시하지 않는다. 초기 UI는 cursor polling을 사용하고 실시간 스트림은 후속으로 추가 가능하다.

중지 명령 body 예:

```json
{
  "schema_version": 1,
  "type": "CANCEL_OPEN",
  "expected_revision": 7,
  "reason": "사용자 운용 중지"
}
```

202 응답 예:

```json
{
  "command_id": "33333333-3333-4333-8333-333333333333",
  "status": "ACCEPTED",
  "desired_state": "PAUSED",
  "observed_state": "CANCELING",
  "pause_epoch": 3
}
```

START/RESUME는 데이터 준비·대사·지원 기능·미확정 주문 검사를 통과해야 RUNNING으로 관측된다. 필수 계좌 정보가 없는 live START는 거절한다. 네트워크 장애 시 ACCEPTED가 영원히 정상처럼 남지 않게 command에 deadline과 ATTENTION 결과를 둔다.

오류 envelope:

```json
{
  "error": {
    "code": "STALE_ACCOUNT_SNAPSHOT",
    "message": "잔고를 다시 확인한 뒤 실행할 수 있습니다.",
    "retryable": true,
    "correlation_id": "audit-trace-id",
    "details": {"account_id": "11111111-1111-4111-8111-111111111111"}
  }
}
```

422: 잘못된 전략/단위/지원 범위. 401/403: 인증/소유권. 409: 상태 충돌·중복키 다른 요청·revision 불일치. 503: 준비 불가. 외부 주문 거부는 요청 API 500으로 숨기지 않고 order 상태와 거부 사유로 보고한다. 내부 예외 원문·토큰·외부 응답 전체를 클라이언트에 노출하지 않는다.

## 9. 설정 파일 의미

[paper-deployment.json](examples/paper-deployment.json)은 계약 fixture다. 실제 실행 예시는 [kis-paper-runner.json](examples/kis-paper-runner.json)과 [us-paper-runner.json](examples/us-paper-runner.json)이며, account ID와 broker 자격증명은 실행 환경에서 바인딩한다.

- strategy와 deployment는 구분해서 저장한다. strategy는 계산 규칙, deployment는 계좌·예산·스케줄·모드다.
- cash_buffer는 미배정 현금 목표이며 target_weights 합은 1-cash_buffer 이하.
- max_asset_weight는 deployment NAV 대비, max_order_notional은 해당 거래 통화 금액.
- max_daily_turnover는 당일 체결 매수+매도 명목금액/NAV_day_start. 일 경계는 risk_day_timezone으로 정의.
- max_drawdown과 daily_loss_limit은 모의 fixture용 값이다. 실거래 한도는 사용자가 정하는 운용 설정으로 분리한다.
- TTL은 시장 휴장 시간을 데이터 장애로 취급하지 않도록 관측 주기/캘린더와 함께 계산한다. 세션 데이터에는 '예정된 최신 봉이 도착했는가'를 우선 검사한다.
- dataset·calendar·cost_model 버전이 다른 백테스트를 같은 재현 결과로 취급하지 않는다.
