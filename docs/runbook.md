# Modelin paper 운영 실행서

## 국내주식 KIS paper

`backend/.env`에 KIS paper 자격증명을 넣은 뒤 프로젝트 루트에서 실행한다.

```powershell
.scripts\start-paper.ps1 -Market krx -IntervalSeconds 300
```

서버가 시작되면 `GET http://127.0.0.1:8000/api/health`에서 `paper_worker`가 `running`인지 확인한다.

## 미국주식

KIS 해외주식 주문 어댑터 구현 전까지 미국주식 worker는 안전을 위해 시작을 차단한다.

## 중지와 안전 규칙

터미널에서 `Ctrl+C`로 서버와 worker를 함께 중지한다. 코인 deployment는 runner가 거절하고, live broker는 기본 등록되지 않는다. 시작 전에 `--once` 실행으로 시장 캘린더와 데이터 공급자를 먼저 확인할 수 있다.
