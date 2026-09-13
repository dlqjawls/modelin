# Modelin 설계 문서

목표: 국장·미장·코인의 전략 판단, 매수·매도, 주문·잔고 추적을 자동으로 수행한다.

1. [코드 진단](autonomous-trading-review.md): 기존 구현의 범위와 계산 오류 재현 결과.
2. [자동 운용 상세 설계](trading-system-design.md): 전략, 데이터, 주문 계획, 위험 검사, 운영 구조.
3. [데이터·API 계약](trading-contracts.md): 타입, 테이블, 주문 상태, 원자성, API.
4. [구현 작업과 검증 기준](trading-implementation-plan.md): 구현 순서와 계산·장애 수용 테스트.
5. [모의 운용 설정 예시](examples/paper-deployment.json): 계약 설명용 가상 계좌 설정.

현재 구현 범위: 백테스트 체결 시점 교정, 공통 전략 validator/runtime, SQLite Paper 원장, 주문 상태·outbox·복구 journal, 계좌 lease/fencing, 위험 한도, v1 운영 API, 시장 데이터 표준화, React Paper 운영 화면, fail-closed broker port, 그리고 application 계층의 계좌·deployment·paper cycle·조회·context·research 서비스. 영속성 구현은 `data/persistence/`, 시장 데이터 계약은 `core/contracts.py`, 외부 provider 조립은 `application/container.py`, paper runtime 조립은 `workers/paper_runtime.py`에 둔다. frontend API 호출과 계약은 각각 `services/`와 `contracts/`로 분리되며 화면은 `App.tsx`에서 lazy loading한다.

## 구조 규칙

`backend/application/ARCHITECTURE.md`에 정의한 의존 방향을 따른다. `core`는 API나 application을 import하지 않으며, application service는 외부 adapter를 직접 생성하지 않는다. `adapters`는 외부 시스템과 ports를 연결하고, 실행용 runtime 조립은 workers에 둔다. 이 규칙은 `backend/tests/test_architecture.py`에서 자동으로 검사한다.

검증 명령:

```powershell
$env:PYTHONPATH="backend"
python -m unittest discover -s backend/tests -v
python -m compileall -q backend
python scripts/check-architecture.py
```

증권사·거래소가 미정인 동안 live adapter는 등록되지 않으며, `DisabledLiveBroker`가 외부 주문·조회·이벤트 호출을 모두 차단한다. PostgreSQL migration은 운영 DB 적용 전 검토가 필요한 foundation SQL이고, 로컬 개발 검증은 SQLite를 사용한다.
