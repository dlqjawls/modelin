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
| Backend | FastAPI, Python 3.12+ |
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

### Supabase 설정

1. [Supabase](https://supabase.com)에서 프로젝트 생성
2. `backend/schema.sql`을 SQL Editor에서 실행
3. `.env` 파일에 `SUPABASE_URL`과 `SUPABASE_KEY` 설정

## 📁 프로젝트 구조

```
modelin/
├── backend/                 # FastAPI 백엔드
│   ├── main.py              # 서버 진입점
│   ├── config.py            # 설정
│   ├── schema.sql           # DB 스키마
│   ├── api/                 # API 라우터
│   ├── core/                # 퀀트 엔진
│   └── data/                # 데이터 프로바이더
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

## ⚠️ 주의사항

- 이 프로그램은 투자 참고용이며, 투자 결정의 책임은 사용자에게 있습니다.
- 자동 매매 기능 사용 시 반드시 Paper Trading으로 충분한 테스트 후 실제 자금을 투입하세요.
- API 키는 절대 코드에 하드코딩하지 마세요. `.env` 파일을 사용하세요.
