# Application layer

`application`은 HTTP나 브로커 SDK에 종속되지 않는 유스케이스 조정 계층이다.

- `container.py`: 저장소·레지스트리·서비스를 조립하는 composition root
- `deployment_service.py`: paper deployment 생성과 계좌·전략 검증
- `paper_cycle.py`: 한 번의 paper 실행 요청을 조정하는 경계

현재 `paper_worker.py`는 기존 실행 로직과 반복 스케줄링을 함께 포함한다. `PaperCycleService`는 호환 가능한 경계를 먼저 제공하며, 다음 단계에서 데이터 준비·전략 평가·주문 제출을 각각 application/domain 서비스로 이동한다. 새 서비스는 어댑터를 생성하지 않고 주입받은 `data_adapter`, `broker`, `journal`만 사용한다.

의존 방향은 다음을 따른다.

```text
api / workers -> application -> core + ports
adapters      -> ports + core data contracts
core          -> 외부 SDK와 API 라우터를 import하지 않음
```
