"""
Modelin - 퀀트 투자 플랫폼 설정
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


class Settings:
    """앱 전역 설정"""

    # === App ===
    APP_NAME: str = "Modelin"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # === Supabase ===
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")  # anon/public key
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")  # service role key

    # === API Keys (Trading) ===
    UPBIT_ACCESS_KEY: str = os.getenv("UPBIT_ACCESS_KEY", "")
    UPBIT_SECRET_KEY: str = os.getenv("UPBIT_SECRET_KEY", "")
    KIS_APP_KEY: str = os.getenv("KIS_APP_KEY", "")
    KIS_APP_SECRET: str = os.getenv("KIS_APP_SECRET", "")
    KIS_ACCOUNT_NO: str = os.getenv("KIS_ACCOUNT_NO", "")
    KIS_ENVIRONMENT: str = os.getenv("KIS_ENVIRONMENT", "paper")
    ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "")
    ALPACA_API_SECRET: str = os.getenv("ALPACA_API_SECRET", "")
    US_PAPER_BROKER: str = os.getenv("US_PAPER_BROKER", "local")
    NEWS_FEEDS: list[str] = [item for item in os.getenv("NEWS_FEEDS", "").split(",") if item]
    OPENDART_API_KEY: str = os.getenv("OPENDART_API_KEY", "")
    SEC_USER_AGENT: str = os.getenv("SEC_USER_AGENT", "")
    SEC_CIKS: list[str] = [item for item in os.getenv("SEC_CIKS", "").split(",") if item]

    # === Server ===
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000"
    ).split(",")

    # === Data ===
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5분
    MAX_OHLCV_DAYS: int = int(os.getenv("MAX_OHLCV_DAYS", "3650"))  # 10년
    PAPER_DB_PATH: str = os.getenv("PAPER_DB_PATH", "modelin-paper.sqlite3")
    PAPER_WORKER_ENABLED: bool = os.getenv("PAPER_WORKER_ENABLED", "false").lower() == "true"
    PAPER_DEPLOYMENT_FILE: str = os.getenv("PAPER_DEPLOYMENT_FILE", "")
    PAPER_WORKER_INTERVAL_SECONDS: int = int(os.getenv("PAPER_WORKER_INTERVAL_SECONDS", "300"))


settings = Settings()
