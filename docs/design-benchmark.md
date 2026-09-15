# Modelin 디자인 벤치마크 및 리팩토링 기준

## 목적

Modelin은 분석 결과와 자동매매 운영 상태를 한 화면에서 빠르게 판단할 수 있어야 한다. 장식보다 데이터 출처, 상태, 위험 신호, 사용 가능한 조작을 우선한다.

## 벤치마크에서 채택한 원칙

| 원칙 | 적용 방법 |
| --- | --- |
| 상태는 짧은 텍스트와 일관된 색으로 표시 | `StatusBadge`, `status-ok`, `status-error` 사용 |
| 표와 목록은 데이터 탐색 영역으로 분리 | `table-container`, `watchlist-scroll`, 카드 내부 도구 영역 사용 |
| 화면마다 목적과 데이터 성격을 먼저 설명 | 공통 `PageHeader`의 제목·설명·상태 배지 사용 |
| 로딩·오류·빈 상태를 구분 | `loading-panel`, `alert`, `empty-state` 사용 |
| 반응형에서도 정보 우선순위를 유지 | 900px에서 사이드바 축소, 600px에서 단일 열 전환 |
| 금융 데이터의 출처를 숨기지 않음 | 대시보드의 `KIS · 읽기 전용`, 운영 화면의 연결 진단 표시 |

## 현재 적용 범위

- 대시보드: KIS 잔고 출처, 오류 상태, 관심종목 행 구조 개선
- 자동매매 운영: Paper 워커 상태와 연결 진단 배지 통일
- 설정: 서버·워커 상태를 공통 상태 배지로 표시
- 백테스트·스크리너·차트·포트폴리오: 공통 페이지 헤더 적용
- 전역 레이아웃: 좁은 화면에서 사이드바·카드·표 재배치
- 헤더: KRX 장중 판정을 한국 시간대와 평일 기준으로 처리
- 사이드바: 클릭 가능한 항목을 버튼으로 변경해 키보드·스크린 리더 의미를 보강

## 남은 개선 순서

1. API 상태 응답에 `updated_at`, `source`, `stale`를 포함해 화면의 최신성 표시를 서버 기준으로 통일한다.
2. 대시보드 자산 곡선은 단일 현재값을 곡선으로 오인하지 않도록 이력 API가 없을 때 스냅샷 상태를 보여준다.
3. 스크리너·백테스트 표에 정렬, 필터, 결과 갱신 시각을 추가한다.
4. 실행 화면의 위험 작업은 버튼 그룹과 확인 상태를 분리해 실수 가능성을 줄인다.
5. 브라우저 기반 시각 회귀 검증을 CI 또는 로컬 체크리스트로 추가한다.

## 참고 기준

- [IBM Carbon Data Table](https://carbondesignsystem.com/components/data-table/usage/): 데이터 탐색 영역에 도구 모음, 정렬, 행 확장을 배치한다. Modelin 적용 위치는 `ScreenerPanel`, `BacktestPanel`의 결과 영역이다.
- [IBM Carbon Status Indicator](https://carbondesignsystem.com/patterns/status-indicator-pattern/): 대시보드와 데이터 표에서 텍스트 라벨과 시각 신호를 함께 사용한다. Modelin 적용 위치는 `StatusBadge`와 운영·진단 화면이다.
- [Material Design 3](https://m3.material.io/): 진행 상태와 반응형 컴포넌트의 계층을 참고한다. Modelin 적용 위치는 공통 `PageHeader`, 로딩·오류·빈 상태다.
