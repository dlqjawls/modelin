"""Run the separately validated KIS US paper deployment.

This entry point is intentionally separate from the domestic KRX runner.
It remains disabled unless ``PAPER_ALLOWED_MARKETS`` contains ``us``.
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import settings
from workers.run_paper import load_deployment, run


def main():
    parser = argparse.ArgumentParser(description="Modelin US KIS paper runner")
    parser.add_argument("deployment", help="US paper deployment JSON")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    deployment = load_deployment(args.deployment, allowed_markets={"us"})
    if "us" not in settings.PAPER_ALLOWED_MARKETS:
        raise SystemExit("us paper 실행은 backend/.env의 PAPER_ALLOWED_MARKETS에 us를 명시해야 합니다.")
    if not settings.KIS_APP_KEY or not settings.KIS_APP_SECRET or not settings.KIS_US_ACCOUNT_NO:
        raise SystemExit("KIS US paper credentials are missing in backend/.env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run(deployment, max(60, args.interval), once=args.once))


if __name__ == "__main__":
    main()
