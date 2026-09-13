# Modelin - 퀀트 투자 플랫폼

한국/미국 주식 및 암호화폐를 위한 올인원 퀀트 투자 플랫폼.

## ✨ 기능

- 📊 **종목 스크리닝** — PER, PBR, ROE 등 팩터 기반 다중 조건 스크리닝
- 📈 **백테스팅** — 벡터화 엔진 기반 고속 전략 백테스팅 (이평선, RSI, 모멘텀, 볼린저밴드 등)
- 🕯️ **차트 분석** — TradingView 스타일 인터랙티브 캔들 차트 + 기술적 지표
- 💼 **포트폴리오 최적화** — 효율적 프론티어, 최대 샤프 비율 (예정)
- 🤖 **자동 매매** — 국내·미국 KIS paper 운용과 운영 화면 지원
- 🌐 **다국어** — 한국어 / English 전환

## 🏗️ 기술 스택

| 구분 | 기술 |
|:---|:---|
| Backend | FastAPI, Python 3.11+ |
| Frontend | React, TypeScript, Vite |
| Database | Supabase (PostgreSQL) |
| Charts | TradingView Lightweight Charts, Recharts |
| Data | pykrx (한국), yfinance (미국), ccxt/Upbit (암호화폐) |

## 🚀 시작하기

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# .env 파일에 Supabase URL/Key 설정
python main.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### 설정 및 실행 상태

로컬 개발과 Paper 검증은 SQLite를 사용한다. PostgreSQL migration은 운영 적용 전 검토 대상이며, 아직 기본 실행 경로가 아니다. API 키와 KIS 자격 증명은 `backend/.env`에만 둔다. `scripts/check-dev-environment.ps1`로 실행 환경을 먼저 확인한다.

## 📁 프로젝트 구조

```
modelin/
├── backend/                 # FastAPI 백엔드
│   ├── main.py              # 서버 진입점
│   ├── config.py            # 설정
│   ├── application/         # 유스케이스와 의존성 조립
│   ├── schema.sql           # DB 스키마
│   ├── api/                 # HTTP 라우터와 응답 변환
│   ├── core/                # 순수 전략·위험·주문 도메인
│   ├── ports/               # 브로커·시장 데이터 인터페이스
│   ├── adapters/            # KIS·데이터 공급자 구현
│   ├── workers/             # 반복 실행과 스케줄링
│   └── tests/               # 회귀·아키텍처 경계 테스트
├── frontend/                # React 프론트엔드
│   └── src/
│       ├── components/      # UI 컴포넌트
│       ├── hooks/           # 커스텀 훅 (i18n 등)
│       └── services/        # API 서비스
└── README.md
```

## 📋 개발 로드맵

- [x] Phase 1: 데이터 레이어 + 기본 인프라
- [x] Phase 2: 종목 스크리닝
- [x] Phase 3: 백테스팅
- [x] Phase 4: 기술적 분석 및 전략 비교
- [x] Phase 5: 포트폴리오 최적화
- [x] Phase 6: 자동 매매 paper 운용 기반

연결 상태를 확인하려면 [운영 실행서](docs/runbook.md)의 읽기 전용 점검을 실행한다. 실제 주문 전에는 paper 계좌에서 사용자가 승인한 종목·수량으로 주문·취소 검증을 별도로 진행해야 한다.

Windows 개발환경 점검은 `powershell -ExecutionPolicy Bypass -File scripts/check-dev-environment.ps1`로 실행한다. Python·Node.js 실행기와 `backend/.env` 존재 여부만 확인하며 비밀값은 출력하지 않는다.

## ⚠️ 주의사항

- 이 프로그램은 투자 참고용이며, 투자 결정의 책임은 사용자에게 있습니다.
- 자동 매매 기능 사용 시 반드시 Paper Trading으로 충분한 테스트 후 실제 자금을 투입하세요.
- API 키는 절대 코드에 하드코딩하지 마세요. `.env` 파일을 사용하세요.
