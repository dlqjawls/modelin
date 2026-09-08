-- ============================================================
-- Modelin - Supabase 데이터베이스 스키마
-- 퀀트 투자 플랫폼용 테이블 정의
-- ============================================================

-- 종목 마스터 테이블
CREATE TABLE IF NOT EXISTS assets (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  name VARCHAR(100) NOT NULL,
  market VARCHAR(10) NOT NULL CHECK (market IN ('krx', 'us', 'crypto')),
  sector VARCHAR(50) DEFAULT '',
  currency VARCHAR(10) DEFAULT 'KRW',
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(symbol, market)
);

-- 가격 데이터 캐시 테이블 (OHLCV)
CREATE TABLE IF NOT EXISTS price_cache (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  market VARCHAR(10) NOT NULL,
  date DATE NOT NULL,
  open DECIMAL(20, 4) NOT NULL,
  high DECIMAL(20, 4) NOT NULL,
  low DECIMAL(20, 4) NOT NULL,
  close DECIMAL(20, 4) NOT NULL,
  volume BIGINT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(symbol, market, date)
);

-- 가격 데이터 인덱스
CREATE INDEX IF NOT EXISTS idx_price_cache_symbol_date ON price_cache(symbol, market, date);

-- 스크리닝 프리셋 테이블
CREATE TABLE IF NOT EXISTS screener_presets (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  name VARCHAR(100) NOT NULL,
  description TEXT DEFAULT '',
  market VARCHAR(10) NOT NULL DEFAULT 'krx',
  conditions JSONB NOT NULL DEFAULT '[]',
  sort_by VARCHAR(50) DEFAULT 'market_cap',
  sort_desc BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 백테스트 결과 저장 테이블
CREATE TABLE IF NOT EXISTS backtest_results (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  name VARCHAR(200) DEFAULT '',
  config JSONB NOT NULL,
  results JSONB NOT NULL,
  total_return DECIMAL(10, 4),
  cagr DECIMAL(10, 4),
  sharpe_ratio DECIMAL(10, 4),
  max_drawdown DECIMAL(10, 4),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 포트폴리오 테이블
CREATE TABLE IF NOT EXISTS portfolios (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  name VARCHAR(100) NOT NULL,
  description TEXT DEFAULT '',
  initial_capital DECIMAL(20, 2) DEFAULT 10000000,
  current_value DECIMAL(20, 2) DEFAULT 0,
  is_paper BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 포트폴리오 포지션 테이블
CREATE TABLE IF NOT EXISTS positions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  portfolio_id UUID REFERENCES portfolios(id) ON DELETE CASCADE,
  symbol VARCHAR(20) NOT NULL,
  market VARCHAR(10) NOT NULL,
  quantity DECIMAL(20, 8) NOT NULL DEFAULT 0,
  avg_price DECIMAL(20, 4) NOT NULL DEFAULT 0,
  current_price DECIMAL(20, 4) DEFAULT 0,
  unrealized_pnl DECIMAL(20, 2) DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 거래 기록 테이블
CREATE TABLE IF NOT EXISTS trades (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  portfolio_id UUID REFERENCES portfolios(id) ON DELETE CASCADE,
  symbol VARCHAR(20) NOT NULL,
  market VARCHAR(10) NOT NULL,
  side VARCHAR(4) NOT NULL CHECK (side IN ('buy', 'sell')),
  quantity DECIMAL(20, 8) NOT NULL,
  price DECIMAL(20, 4) NOT NULL,
  fee DECIMAL(20, 4) DEFAULT 0,
  is_paper BOOLEAN DEFAULT true,
  executed_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 관심 종목 테이블
CREATE TABLE IF NOT EXISTS watchlist (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  symbol VARCHAR(20) NOT NULL,
  market VARCHAR(10) NOT NULL,
  notes TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, symbol, market)
);

-- RLS (Row Level Security) 정책
ALTER TABLE screener_presets ENABLE ROW LEVEL SECURITY;
ALTER TABLE backtest_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist ENABLE ROW LEVEL SECURITY;

-- 사용자별 데이터 접근 정책
CREATE POLICY "Users can manage their own screener presets"
  ON screener_presets FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users can manage their own backtest results"
  ON backtest_results FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users can manage their own portfolios"
  ON portfolios FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users can manage positions in their portfolios"
  ON positions FOR ALL
  USING (portfolio_id IN (SELECT id FROM portfolios WHERE user_id = auth.uid()));

CREATE POLICY "Users can manage trades in their portfolios"
  ON trades FOR ALL
  USING (portfolio_id IN (SELECT id FROM portfolios WHERE user_id = auth.uid()));

CREATE POLICY "Users can manage their own watchlist"
  ON watchlist FOR ALL
  USING (auth.uid() = user_id);

-- 가격 캐시는 전체 읽기 허용
ALTER TABLE price_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Price cache is readable by everyone"
  ON price_cache FOR SELECT
  USING (true);

-- 종목 마스터는 전체 읽기 허용
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Assets are readable by everyone"
  ON assets FOR SELECT
  USING (true);
