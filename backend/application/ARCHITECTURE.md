# Application layer

`application`은 HTTP나 브로커 SDK에 종속되지 않는 유스케이스 조정 계층이다.

- `container.py`: 저장소·레지스트리·서비스와 외부 provider를 조립하는 composition root
- `deployment_service.py`: paper deployment 생성과 계좌·전략 검증
- `paper_cycle.py`: 한 번의 paper 실행 요청을 조정하는 경계
- `paper_context.py`: 주입받은 뉴스·macro·공시 provider의 결과를 전략 context로 변환
- `market_data_service.py`: 시장별 provider 접근을 한 곳으로 제공
- `backtest_service.py`, `portfolio_service.py`, `screener_service.py`: research 유스케이스를 조정

`paper_worker.py`는 반복 실행과 외부 진입점 역할을 담당하고, 한 사이클의 준비·결정·실행은 application service로 위임한다. `workers/paper_runtime.py`는 KIS와 시장 데이터 provider를 paper 실행용으로 조립한다. application service는 어댑터를 생성하지 않고 주입받은 `data_adapter`, `broker`, `journal`과 provider factory만 사용한다.

의존 방향은 다음을 따른다.

```text
api / workers -> application -> core + ports
adapters      -> ports + core data contracts
core          -> 외부 SDK와 API 라우터를 import하지 않음
```

`application/container.py`는 외부 구현을 연결하는 유일한 composition root다. 하나의 `MarketDataService` 인스턴스를 백테스트·포트폴리오·스크리너가 공유해 provider 수명주기와 설정을 일관되게 유지한다. 테스트에서는 provider factory와 broker/data adapter를 가짜 구현으로 주입할 수 있다. 실행 프로세스의 runtime 조립은 `workers/paper_runtime.py`에 두어 유스케이스 계층이 KIS SDK나 provider 생성 방식에 의존하지 않도록 한다.
